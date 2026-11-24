"""Our sourced-data chart design; not an official LinkFox size-chart template."""
import io
from PIL import Image,ImageDraw,ImageFont,ImageChops
from pathlib import Path

def face(size,bold=False,serif=False):
    name=('georgiab.ttf' if bold else 'georgia.ttf') if serif else ('arialbd.ttf' if bold else 'arial.ttf')
    root=Path('C:/Windows/Fonts');return ImageFont.truetype(str(root/name),size)

def editorial(preview,chart):
    columns=chart['columns'];rows=chart['rows']
    if not 2<=len(columns)<=6 or not 1<=len(rows)<=8 or any(len(row)!=len(columns) for row in rows):
        raise ValueError('尺码表数据量超出清晰排版范围')
    canvas=Image.new('RGB',(2000,2000),'white');draw=ImageDraw.Draw(canvas)
    ink='#272725';accent='#8A5B3D';line='#DED6CC';subtle='#6A6762'
    draw.rectangle((1000,0,2000,2000),fill='#F7F1E8')
    draw.text((1080,140),'SIZE & FIT',font=face(104,True,True),fill=ink)
    draw.text((1084,310),'Garment measurements  /  '+str(chart['units']),font=face(38),fill=subtle)
    draw.line((1080,430,1920,430),fill=accent,width=3)
    # Only trim outer white studio margins, without changing foreground pixels.
    # The crop is bounded by all nonwhite content and padded; no garment mask,
    # hand coordinates, synthesized structure or colour adjustment is used.
    photo=preview.convert('RGB');diff=ImageChops.difference(photo,Image.new('RGB',photo.size,'white'))
    mask=diff.convert('L').point(lambda x:255 if x>12 else 0);bounds=mask.getbbox()
    if bounds:
        pad=round(max(photo.size)*.025)
        crop=[max(0,bounds[0]-pad),max(0,bounds[1]-pad),min(photo.width,bounds[2]+pad),min(photo.height,bounds[3]+pad)]
    else:crop=[0,0,photo.width,photo.height]
    photo=photo.crop(crop);photo.thumbnail((970,1900),Image.Resampling.LANCZOS)
    canvas.paste(photo,((1000-photo.width)//2,2000-photo.height))
    x0,x1=1080,1920;width=x1-x0;colwidth=width/len(columns);top=520
    header_height=185;row_height=min(255,1030//len(rows))
    draw.line((x0,top,x1,top),fill=accent,width=5)
    for index,label in enumerate(columns):
        text=str(label);font_size=48;parts=text.split()
        if draw.textlength(text,font=face(font_size,True))>colwidth-22 and len(parts)==2:text='\n'.join(parts)
        while font_size>28 and max(draw.textlength(line,font=face(font_size,True)) for line in text.split('\n'))>colwidth-22:font_size-=1
        if max(draw.textlength(line,font=face(font_size,True)) for line in text.split('\n'))>colwidth-22:raise ValueError('尺码表列标题过长')
        draw.multiline_text((x0+colwidth*(index+.5),top+header_height/2),text,anchor='mm',align='center',spacing=8,font=face(font_size,True),fill=accent)
    draw.line((x0,top+header_height,x1,top+header_height),fill=line,width=2)
    for n,row in enumerate(rows):
        y=top+header_height+n*row_height
        for col,value in enumerate(row):
            label=str(value);font_size=70 if col==0 else 66
            while font_size>32 and draw.textlength(label,font=face(font_size,col==0))>colwidth-22:font_size-=1
            if draw.textlength(label,font=face(font_size,col==0))>colwidth-22:raise ValueError('尺码表数值单元格过长')
            draw.text((x0+colwidth*(col+.5),y+row_height/2),label,anchor='mm',font=face(font_size,col==0),fill=ink)
        draw.line((x0,y+row_height,x1,y+row_height),fill=line,width=2)
    output=io.BytesIO();canvas.save(output,'PNG')
    return output.getvalue(),{'style':'editorial-split-v1','rendererVersion':2,'source':'independent workbench layout inspired by editorial typography; no dedicated official size template found',
        'photoCropPixels':crop,'allSourceValuesRetained':True,'chartColumns':columns,'chartRows':rows,'units':chart['units'],'garmentPixelsRepainted':False}
