from PIL import Image,ImageDraw
import image_provider
import io
from pathlib import Path
codes=['ccBP9h25kp0qeNRx6','wh9uwO25kp0raHjUR','fUeVhf25kp0k0yFqv','JIPqej25kp0osBiFW','y6U33e25kp0vZsDws','qWhy4625kp0iXmSXc']
canvas=Image.new('RGB',(900,640),'white')
draw=ImageDraw.Draw(canvas)
out=Path('data/batch-20261030/source-D2')
out.mkdir(exist_ok=True)
for n,code in enumerate(codes):
    path=out/(str(n)+'.webp')
    if not path.exists():
        raw,mime=image_provider.remote_reference('https://cbu01.alicdn.com/img/ibank/O1CN01'+code+'_!!980537565-0-cib.jpg_.webp')
        path.write_bytes(raw)
    image=Image.open(path).convert('RGB')
    image.thumbnail((290,290))
    canvas.paste(image,((n%3)*300,(n//3)*320+20))
    draw.text(((n%3)*300+5,(n//3)*320+3),str(n),fill='black')
canvas.save(out/'contact.jpg')
print(out/'contact.jpg')
