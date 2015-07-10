sc = window.sc || {};
sc.popup = {
    isPopupHover: false,
    popups: [],
    popup: function(parent, popup, protected) {
        console.log('Creating popup', [parent, popup, protected]);
        var self = this,
            offset,
            docWith,
            dupe,
            docWidth,
            isAbsolute = false,
            markupTarget = $('#text');
        if (self.isPopupHover) {
            return false
        }
        
        if (markupTarget.length == 0) {
            markupTarget = $('main');
            if (markupTarget.length == 0) {
                markupTarget = $('body');
            }
        }
        if ('left' in parent || 'top' in parent) {
            offset = parent
            offset.left = offset.left || 0
            offset.top = offset.top || 0
            parent = document.body
            isAbsolute = true

        } else {
            parent = $(parent)
            offset = parent.offset()
        }
        popup = $('<div class="text-popup"/>').append(popup);

        //We need to measure the doc width now.
        docWidth = $(document).width()
        // We need to create a dupe to measure it.
        dupe = $(popup).clone()
            
        markupTarget.append(dupe)
        var popupWidth = dupe.innerWidth(),
            popupHeight = dupe.innerHeight();
        dupe.remove()
        //The reason for the duplicity is because if you realize the
        //actual popup and measure that, then any transition effects
        //cause it to zip from it's original position...
        if (!isAbsolute) {
            offset.top += parent.innerHeight() - popupHeight - parent.outerHeight();
            offset.left -= popupWidth / 2;
        }

        if (offset.left < 1) {
            offset.left = 1;
            popup.innerWidth(popupWidth + 5);
        }
        
        if (offset.left + popupWidth + 5 > docWidth)
        {
            offset.left = docWidth - (popupWidth + 5);
        }
        popup.offset(offset)
        markupTarget.append(popup)
        popup.offset(offset)
        popup.mouseenter(function(e) {
            self.isPopupHover = true
        });
        
        popup.mouseleave(function(e){
                if (protected) {
                    return
                }
                $(this).remove();
                self.isPopupHover = false
            });
        this.clear();
        if (protected) {
            popup.data('protected', protected);
        }
        this.popups.push(popup);
        return popup;
    },
    clear: function(clearProtected) {
        var keep = [];
        this.popups.forEach(function(e) {
            if (!clearProtected && e.data('protected')) {
                keep.push(e);
                console.log('Keeping ', e);
            } else {
                e.remove();
            }
        });
        this.popups = keep;
        this.isPopupHover = false;
    }
}
