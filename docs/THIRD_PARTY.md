# Third-party notices and redistribution

Dependencies are installed from their publishers; proprietary SDK binaries are not committed.

| Component | Role | Licence information |
| --- | --- | --- |
| Python | Runtime | Python Software Foundation licence |
| PySide6 / Qt | Desktop interface and multimedia | LGPL/GPL/commercial options; retain the licence files shipped with the selected distribution and meet its applicable terms |
| Pillow | Image loading and editing | HPND |
| openpyxl | XLSX import | MIT |
| pydicom / pynetdicom | DICOM objects and networking | MIT |
| imageio-ffmpeg | FFmpeg launcher and bundled encoder | Python wrapper BSD-2-Clause; the bundled FFmpeg binary has its own build-dependent LGPL/GPL terms |
| PyInstaller | Windows packaging | GPL with its published distribution exception |
| Inno Setup | Windows installer | Inno Setup licence |
| Canon EDSDK | Optional Canon camera integration | Proprietary Canon SDK licence; obtain separately and follow Canon's redistribution terms |
| CSO drivers / SDK | Optional Mizar integration | Supplied separately by CSO or its authorised provider |

The preview recorder uses FFmpeg with libx264. Do not assume the encoder binary has the same licence as the Python wrapper. Review its build configuration, retain notices and satisfy source/distribution obligations before external redistribution. Qt libraries remain dynamically linked in the application bundle. This project does not grant a licence to proprietary SDKs or to patient images.
