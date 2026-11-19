# SCHP ATR local body parsing

The automatic clothing selector uses the pinned, MIT-licensed SCHP ATR-18
INT8 ONNX conversion from `pirocheto/schp-atr-18`, revision
`61f4ff3c508b899904e495cefbbaff9cacadeb45`. Its source architecture is
[PeikeLi/Self-Correction-Human-Parsing](https://github.com/PeikeLi/Self-Correction-Human-Parsing).
The model card declares MIT. The original MIT notice is included beside it.

Run `python install_colour_models.py` from the workbench folder to restore
the model. The installer and runtime both verify the manifest SHA256.
Inference runs locally in ONNX Runtime. No downloaded Python is executed.

Preprocessing follows the original SCHP extractor's OpenCV BGR channel order
and BGR-indexed mean/std; the conversion's sample image processor describes
RGB, which changes predictions for these weights. Scores are resized before
class argmax, preserving boundaries between body and clothing labels.

Body labels are proposals, not ground truth. Cropped sleeves can be called
pants/arms, and a size chart can be called clothing. The workbench uses
hair/accessory cores and colour-supported skin for protection; automatic SAM
candidate selection and source-pixel refinement determine the clothing mask.
It never unions the entire semantic prediction into a certain clothing mask.
Fine hair, similar-colour overlapping objects and unusual crops remain
limitations and require the normal output checks.
