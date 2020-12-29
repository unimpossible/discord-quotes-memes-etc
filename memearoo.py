#!/usr/bin/env python
from PIL import Image, ImageFont, ImageDraw
import sys
import argparse
import textwrap

MARGIN = 5

def drawOutline(draw, pos, outlineSize, text, font):
    x = pos[0]
    y = pos[1]
    draw.text((x - outlineSize, y),\
              text, font=font, fill="black")
    draw.text((x + outlineSize, y), \
              text, font=font, fill="black")
    draw.text((x, y - outlineSize), \
              text, font=font, fill="black")
    draw.text((x, y + outlineSize), \
              text, font=font, fill="black")

def IntelliDraw(drawer,text,font,containerWidth):
    if not text:
        return ("", 0, 0)
    words = text.split()

    #lines = [] # prepare a return argument
    #lines.append(words)
    #finished = False
    #line = 0
    #while not finished:
    #    thistext = lines[line]
    #    newline = []
    #    innerFinished = False
    #    while not innerFinished:
    #        print('thistext: '+str(thistext))
    #        if drawer.textsize(' '.join(thistext),font)[0] > containerWidth:
    #            print(drawer.textsize(' '.join(thistext),font)[0])
    #            # this is the heart of the algorithm: we pop words off
    #            # sentence until the width is ok, then in the next outer loop
    #            # we move on to the next sentence. 
    #            newline.insert(0,thistext.pop(-1))
    #        else:
    #            innerFinished = True
    #    if len(newline) > 0:
    #        lines.append(newline)
    #        line = line + 1
    #    else:
    #        finished = True
    #tmp = []
    #for i in lines:
    #    tmp.append( ' '.join(i) )
    #lines = tmp

    # start with an educated guess
    # Decrement until we find a size that will fit the entire string. This
    # helps account for long words and the fact that all characters are not
    # equal size.
    cW, cH = font.getsize("-")
    ncharacters = int(containerWidth / (cW))
    if (ncharacters == 0):
        ncharacters = 1

    finished = False
    while not finished:
        lines = textwrap.wrap(text,
                              ncharacters,
                              break_long_words=True)
        lines = "\n".join(lines)
        (width, height) = drawer.multiline_textsize(lines, font)

        if width > containerWidth:
            ncharacters = ncharacters -1
        else:
            finished = True

    #(width,height) = drawer.multiline_textsize(lines, font)
    _ , descent = font.getmetrics()
    height += descent
    return (lines,width,height)

def meme_top_bottom_image(strTop, strBot, filename):
    borderWidth = 2
    textSegments = 0
    if (strTop):
        textSegments +=1
    if (strBot):
        textSegments +=2
    addForBorder = borderWidth * textSegments

    img = Image.open(filename)
    imageSize = img.size

    fontSize = int(imageSize[0]/18)
    font = ImageFont.truetype("arial-unicode-ms.ttf", fontSize)

    draw = ImageDraw.Draw(img)
    top_lines, top_textW, top_textH = IntelliDraw(draw, strTop, font, imageSize[0] - 2 * MARGIN)
    bot_lines, bot_textW, bot_textH = IntelliDraw(draw, strBot, font, imageSize[0] - 2 * MARGIN)
    del draw

    totalTopTextH = top_textH
    totalBotTextH = bot_textH

    textFullH = totalTopTextH + totalBotTextH
    newSize = (imageSize[0], imageSize[1] + textFullH + addForBorder)
    imgOut = Image.new("RGB", newSize)
    # Fill with white first
    imgOut.paste("white", (0, 0, newSize[0], newSize[1]))

    # drop in image
    if (strTop == None):
        imageYStart = 0
    else:
        imageYStart = totalTopTextH + borderWidth

    imgOut.paste(img, (0, imageYStart))

    draw = ImageDraw.Draw(imgOut)

    if (strTop != None):
        textYStart = 0
        draw.multiline_text((MARGIN, textYStart), \
                  top_lines, font=font, fill="black")

    if (strBot != None):
        textYStart = imageSize[1] + totalTopTextH + borderWidth
        if (strTop != None):
            textYStart += borderWidth
        draw.multiline_text((MARGIN, textYStart), \
                  bot_lines, font=font, fill="black")

    return imgOut

if __name__ == '__main__':
    print("Hello Memearoo!")
    #meme_image("Hello", "Ripperoni pizza", "standard.jpg")
    img = meme_top_bottom_image("Top line"*7, "Bottom line"*6, "standard.jpg")
    img.save("temp.png")

    print("Goodbye")
