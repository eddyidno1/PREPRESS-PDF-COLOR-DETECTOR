"""checkpdf — detect RGB and spot colors in a PDF and produce a visual report.

A PDF is considered print-safe (PASS) when every color it uses is DeviceCMYK
or DeviceGray. Any RGB-class color (DeviceRGB, RGB ICC, CalRGB, Lab, Indexed
on an RGB base) or spot color (Separation / DeviceN) is flagged (FAIL).
"""

__version__ = "1.0.0"
