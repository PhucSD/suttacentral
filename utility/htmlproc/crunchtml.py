"""Now you all be squishies!

Crunchtml works in conjunction with HTML5 tidy, taking HTML generated by
WYSIWYG applications and destructively transforming it, such that it becomes
both more  regular and more comprehensible. In particular Crunchtml takes
'nested tags' such as: 
<p><font color="#0000FF"><b><i><strong>Pacankes!</b></i></font></p> 
and "Crunches" them, into a single tag: 
<p class="blue bold italic">Pancakes!"</p>

All qualities of all the nested tags, are 'inherited' by the outermost tag.
Duplicates are eliminated from the class list and it is sorted
alphabetically, meaning that <h1><b><i>Hello World!</i></b></h1> and
<h1><em><b>Hello Cruel World!</b></em></h1> produce identical markup (<h1
class="bold italic">). Note that <b>, <strong>, <i>, and <em> are converted
into css styles when they are an only child, otherwise they remain untouched.
Also only certain tags are 'crunchy', the  default list being <div>, <span>,
<b>, <i>, <strong>, <em>

It should be stressed that the goal is to create an intermediate HTML file
for further processing. It makes no instrinsic sense to have an element  
<p class="blue bold center"> in production HTML. Rather, that should be
converted into properly styled HTML, for example, <h2>. Crunchtml saves you
the donkey work of figuring out all the possible permutations of making text
"blue, bold and centered" (i.e. how the original author conceived of a
section heading or whatever). The huge variation in how these can appear in
the HTML produced by the word processor can be a result of things like
changes in user pattern (the user might start with manually bolding things,
then move to styles), different versions of the application (it might change
from b to strong) and simply the insane whim of the application. When many
seperate documents are converted, there is no guarantee that the classes will
be named the same in each document, since often the classes are just formed
by prefix+number.

Where possible color codes will be converted to color names, with a margin of
error permitted, meaning that #000080 and #00007f will both be called "navy".
By default 20% error is permitted.

"""

import env
import logging, regex, os, os.path, time, subprocess
import tools.html, pathlib, collections, io
from .colors import color_name


BRTAG_SAFE = 1
BRTAG_UNSAFE = 2

def generate_descriptive_name(attr, value):
    if attr in {'color', 'background', 'background-color'}:
        if value.startswith('#'):
            color = color_name(value, 0)
            if color is not None:
                name = color[0]
            else:
                name = 'color' + value[1:]
        else:
            name = value
        if attr.startswith('background'):
            value = "bg " + value
    elif attr in {'text-align'}:
        name = 'text ' + value
    else:
        name = attr + ' ' + value
    
    name = name.replace('-', ' ')
    name = name.title()
    name = name.replace('%', 'pc')
    name = name.replace(' ', '')
    
    return name

tag_to_class = {"strong": "bold", "b": "bold",
                "em": "italic", "i": "italic",
                "center": "center"}

tag_classes = {"bold": ("font-weight", "bold"),
                "italic": ("font-style", "italic"),
                "center": ("margin", "auto")}

crunchables = {"span", "div", "font", "b", "strong", "i", "em", "center"}

def crunch(root, name_mapping, xml_tags=False):
    for e in list(root.iter()):
        classes = []
        eclass = e.attrib.get('class', None)
        if eclass:
            classes.append(name_mapping.get(eclass, eclass))
        while len(e) == 1:
            if e.text not in {'', '\n', None}:
                break
            child = e[0]
            if child.tag not in crunchables:
                break
            if child.tail not in {'', '\n', None}:
                break

            for attr, value in child.attrib.items():
                if attr == 'class':
                    cclass = child.attrib['class']
                    classes.append(name_mapping.get(cclass, cclass))
                else:
                    # A childrens attrs take precedence over parents (usually)
                    e.attrib[attr] = value
                    
            if child.tag in tag_to_class:
                classes.append(tag_to_class[child.tag])
            child.drop_tag()
        if classes:
            class_string = " ".join(sorted(classes))
            if xml_tags:
                class_string = class_string.replace(' ', '')
                class_string = regex.sub(r'\b(\p{lower})', lambda m: m[0].upper(), class_string)
                e.tag = e.tag + class_string
                try:
                    del e.attrib['class']
                except KeyError:
                    pass
            else:
                e.attrib['class'] = class_string

brackets = {'(': ')', '[': ']'}
bracket_class = {'(': 'RoBr', '[': 'SqBr'}
def convert_brackets_dom(root):
    """ Sometimes people like to be prats and generate constructions like:
    <p>[<em>This is probably a title</em>]</p>
    
    The problem is these horrid constructions can appear in variants:
    <p><em>[This is probably a title]</em></p>
    
    
    The variations on the obscene things one can do with brackets is enough
    to motivate one to turn them into nice crunchy tags.
    
    This function has trouble when the open and close tags are at different
    depths.
    <p><b><i>[This is probably a title</i>]</b></p>
    
    In this case the regex mode should be used.
    
    
    """
    
    for e in root:
        class_ = None
        if not e.text:
            continue
        if e.text[0] in brackets:
            if len(e) > 0:
                if e[-1].tail[-1] == brackets[e.text[0]]:
                    class_ = bracket_class[e.text]
                    e.text = e.text[1:] or None
                    e[-1].tail = e[-1].tail[:-1] or None
        else if e.text[0] in brackets and e.text[-1] == brackets[e.text[0]]:
            e.text = e.text[1:-1]
            class_ = bracket_class[e.text[0]]
        if class_:
            e.wrap_inner(e.makelement('span', {'class':class_}))
            
def convert_brackets_regex(data, mode):
    """ Regex mode doesn't give a damn about mismatched tag depth ;).
    
    """
    
    def repl(m):
        class_ = bracket_class[m[0]].encode()
        return b'<span class="' + class_  + b'">'+ m[1] + b'</span>'
    if mode == BRTAG_UNSAFE:
        # Round brackets
        data = regex.sub(rb'(?>=\w>)\(([^)(]{1,300})\)(?=<\w)', repl, data)
        # Square brackets.
        data = regex.sub(rb'(?>=\w>)\[([^)(]{1,300})\](?=<\w)', repl, data)

    return data

def prune_most_common_face(root):
    # Eliminate spammy explicit font declarations.
    # Recognizing that fonts may contain information, we only
    # remove the most common one, and only if it is significantly
    # more common than the second most common.
    
    faces = root.cssselect('[face]')
    counts = collections.Counter(e.attrib['face'] for e in faces)
    
    if len(counts) == 1:
        for e in faces:
            del e.attrib['face']
    else:
        (fontname, first_n), (_, second_n) = counts.most_common(2)
        if first_n > second_n * 2:
            for e in faces:
                if e.attrib['font'] == fontname:
                    del e.attrib['font']
        
    
tidy_cmd = """tidy -c -w 0 --doctype html5 --quote-nbsp no
    --logical-emphasis yes --merge-emphasis yes --force-output yes --quiet yes
    --drop-proprietary-attributes yes --tidy-mark no --sort-attributes alpha 
    --output-html yes --output-encoding utf8 --css-prefix TIDY""".split()
    
def crunch_file(filepath, xml_tags=False, brtags=BRTAG_SAFE):
    filename = str(filepath)
    doc = tools.html.parse(filename)
    root = doc.getroot()
    prune_most_common_face(root)
    data = tools.html._html.tostring(root, encoding='utf8')
 
    pTidy = subprocess.Popen(tidy_cmd, stdin = subprocess.PIPE, stdout = subprocess.PIPE)
    data = pTidy.communicate(data)[0]
    try:
        pTidy.kill()
    except:
        pass
    del doc, root
    
    if brtag_mode == BRTAG_UNSAFE:
        data = convert_brackets_regex(data)
    
    doc = tools.html.parse(io.BytesIO(data), encoding='utf8')
    
    css = doc.find('//style').text
    print(css)
    new_css = ['/* Unmodified rules */']
    
    new_css_rules = set()
    
    tidyclass_to_newclass = {}
    for line in css.split('\n'):
        m = regex.match(r'\s*(?<element>[\w]+)\.(?<class>TIDY-[0-9]+)\s*\{(\s*(?<attr>[\w-]+):\s*(?<value>[\w #%-]+);?)+\}', line)
        if m:
            css_class = m["class"]
            element = m["element"]
            pairs = list(zip(m.captures("attr"), m.captures("value")))
            
            classes = []
            
            for pair in pairs:
                name = generate_descriptive_name(*pair)
                classes.append(name)
                new_css_rules.add((name, pair))
            
            classes.sort()
            tidyclass_to_newclass[css_class] = " ".join(classes)
        else:
            new_css.append(line)
        
    new_css.append("/* Automatically Generated Classes */")
    new_css_rules.update(tag_classes.items())
    
    new_css.extend("%s {%s: %s}" % (name, prop, val) 
                    for name, (prop, val) in new_css_rules)
    
    new_css_text = "\n".join(new_css) + '\n'
    print(new_css_text)
    doc.find('//style').text = new_css_text
    print(tidyclass_to_newclass)
    crunch(doc.getroot().body, tidyclass_to_newclass, xml_tags=xml_tags)
    return doc