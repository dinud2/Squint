"""C2: get both models into ONNX.

1. MobileNetV3-Small (ImageNet weights, torchvision) exported as an *embedding*
   model: input float32 [1,3,224,224] (RGB, ImageNet-normalised),
   output [1,1024] (the layer before the classifier's last Linear).
2. MoveNet SinglePose Lightning, already ONNX (Xenova/movenet-singlepose-lightning):
   input int32 [1,192,192,3] RGB 0..255, output [1,1,17,3] = (y, x, score).

Run once on a laptop with torch installed; copy models/*.onnx to the Pi.
"""
import os
import urllib.request

import torch
import torchvision

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "models")
MOVENET_URL = "https://huggingface.co/Xenova/movenet-singlepose-lightning/resolve/main/onnx/model.onnx"


class Embed(torch.nn.Module):
    def __init__(self):
        super().__init__()
        m = torchvision.models.mobilenet_v3_small(weights="IMAGENET1K_V1").eval()
        self.features, self.pool = m.features, m.avgpool
        self.head = torch.nn.Sequential(*list(m.classifier.children())[:2])  # Linear(576,1024)+Hardswish

    def forward(self, x):
        return self.head(torch.flatten(self.pool(self.features(x)), 1))


def main():
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "mobilenetv3_small_embed.onnx")
    torch.onnx.export(Embed().eval(), torch.zeros(1, 3, 224, 224), path,
                      input_names=["input"], output_names=["embedding"], opset_version=13,
                      dynamo=False)
    print("wrote", path)
    mv = os.path.join(OUT, "movenet_lightning.onnx")
    if not os.path.exists(mv):
        urllib.request.urlretrieve(MOVENET_URL, mv)
        print("downloaded", mv)


if __name__ == "__main__":
    main()
