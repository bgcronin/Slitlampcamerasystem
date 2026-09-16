# Camera setup and compatibility

## Canon EOS 200D II, EOS 60D and EOS 70D

Canon lists these models in its [EDSDK compatibility information](https://asia.canon/en/campaign/developerresources/sdk). Check the specific SDK release, Windows version and firmware together. A compatibility listing is not a completed application acceptance test.

1. Obtain the Windows **64-bit** EDSDK from Canon under its applicable licence. Use a currently supported release that lists the camera. Keep `EDSDK.dll`, `EdsImage.dll` and any supplied runtime dependencies in their official layout.
2. Connect one camera with a reliable USB data cable and stable power. Close EOS Utility or other software that owns its connection.
3. Set the body to an appropriate photographic mode and **JPEG or RAW+JPEG**. Configure manual focus where autofocus cannot lock on the slit lamp image. Camera mode can limit which exposure controls are writable.
4. In Slitlamp Studio Settings, select the folder containing the x64 `EDSDK.dll`.
5. Select the Canon option and connect. The detected body name should replace the generic label.
6. Capture a test photograph; check its dimensions and fidelity against the camera's own output. Repeat for presets, RAW+JPEG, reconnect and low-storage handling.

Implementation details:

- EDSDK initialisation, native callbacks, event processing, property writes and downloads run on one COM-initialised worker thread.
- Downloads are written to staging and assigned using an immutable capture ticket.
- RAW+JPEG companion files are retained separately with a shared capture-group identifier.
- One capture is outstanding at a time. Following an interrupted request, reconnect before capturing again; late files remain unassigned.
- Live-view frames are decoded for preview. Recording writes that preview stream to MP4 at 15 fps. It does **not** remotely record/download the camera's native movie mode. Metadata and the UI identify this limitation.
- Capture via F5 or the on-screen button for automatic patient assignment. Unsolicited shutter files are quarantined for explicit review. Do not trigger additional camera shots while an application capture is transferring.

## CSO Mizar

Mizar is the CSO camera family specifically requested for this project. CSO's public [product catalogue](https://csoitalia.it/en/products/) lists Mizar, and its [manufacturer announcement](https://csoitalia.it/news/escrs-european-society-of-cataract-and-refractive-surgeons/) describes the 5 MP digital camera. These sources do not provide a usable public SDK contract.

**Do not assume that a USB 3 connection implies UVC or a generic Windows camera interface.** Different installed drivers can expose different interfaces.

### Determine the integration route

On the actual Windows capture PC:

1. Install the CSO-approved camera driver and confirm acquisition in Phoenix.
2. Run Slitlamp Studio → **Camera → Connection diagnostic**. Inspect whether Mizar appears among visible Windows camera devices and which formats it exposes.
3. For driver details, run the read-only script:

```powershell
./scripts/camera_diagnostic.ps1
```

It writes `camera-diagnostic.json` containing camera/device names, hardware IDs and driver provider/version. It reads no patient images or records. The file is excluded from Git.

### If Windows exposes a usable camera device

Select that device and connect. Test native still capture, actual image dimensions, colour rendering, available exposure/white-balance controls and video. Do not accept a low-resolution preview as evidence of full-resolution still support. Hardware joystick events are not assumed to be supported by this generic interface.

### If Mizar requires Phoenix

Use Phoenix to capture, then export photographs/videos into a dedicated folder outside the Slitlamp Studio archive. Configure this folder in Settings. Files are copied into **Import inbox** after their size and modification time stabilise. The operator confirms patient and eye before assignment.

This route depends on the installed Phoenix version's export facility. It is an import workflow, not remote Mizar control. A manufacturer-provided SDK or documented interface is needed to finish proprietary direct control when no standard device interface is exposed.

### Information needed from CSO/supplier for a native adapter

- Exact Mizar model/revision and USB hardware identifiers.
- Supported x64 Windows driver and SDK, redistribution terms and sample acquisition code.
- Device discovery, pixel formats, colour conversion and full-resolution capture APIs.
- Exposure/gain/white-balance controls and capability queries.
- Video acquisition and joystick/foot-pedal trigger events.
- Reconnection, buffer ownership and SDK threading requirements.

## Compatibility register

| Model / route | Implementation | Actual hardware result |
| --- | --- | --- |
| EOS 200D II / EDSDK | Implemented | Not yet tested on hardware |
| EOS 60D / EDSDK | Implemented | Not yet tested on hardware |
| EOS 70D / EDSDK | Implemented | Not yet tested on hardware |
| Mizar / Windows device | Generic adapter implemented; contingent on driver exposure | Not yet established |
| Mizar / Phoenix exported files | Review inbox implemented | Installed Phoenix export behaviour needs testing |
| Mizar / proprietary SDK | Waiting for documented vendor interface | Not implemented |
| Demonstration camera | Generated image and video | Automated simulation tests only |
