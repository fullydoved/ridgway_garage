from PIL import Image, ImageDraw, ImageFont
import sys

# Create a 256x256 image with transparency
size = 256
img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Draw a simple speedometer/gauge icon
# Outer circle (dark background)
draw.ellipse([20, 20, 236, 236], fill='#1a1a1a', outline='#00ff00', width=8)

# Inner dial area
draw.ellipse([50, 50, 206, 206], fill='#0d0d0d', outline='#006600', width=4)

# Speedometer needle (pointing up-right like high speed)
center_x, center_y = 128, 140
needle_length = 70
import math
angle = -45  # degrees (pointing to upper right)
angle_rad = math.radians(angle)
end_x = center_x + needle_length * math.cos(angle_rad)
end_y = center_y + needle_length * math.sin(angle_rad)

# Draw needle with thickness
draw.line([(center_x, center_y), (end_x, end_y)], fill='#ff0000', width=6)

# Center dot
draw.ellipse([118, 130, 138, 150], fill='#ff0000', outline='#ffffff', width=2)

# Tick marks
for i in range(0, 180, 20):
    angle_rad = math.radians(i - 90)
    start_x = center_x + 75 * math.cos(angle_rad)
    start_y = center_y + 75 * math.sin(angle_rad)
    end_x = center_x + 85 * math.cos(angle_rad)
    end_y = center_y + 85 * math.sin(angle_rad)
    draw.line([(start_x, start_y), (end_x, end_y)], fill='#00ff00', width=3)

# Save as ICO with multiple sizes
img_16 = img.resize((16, 16), Image.Resampling.LANCZOS)
img_32 = img.resize((32, 32), Image.Resampling.LANCZOS)
img_48 = img.resize((48, 48), Image.Resampling.LANCZOS)
img_64 = img.resize((64, 64), Image.Resampling.LANCZOS)

img.save('app.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)])
print("Icon created successfully!")
