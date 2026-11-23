"""Convert the free phoneme model (facebook/wav2vec2-xlsr-53-espeak-cv-ft,
Apache-2.0) to a small ONNX file the Android app runs on the phone.
Writes OUT_DIR/w2v_int8.ort (~320 MB, ONNX Runtime's mobile format, which the
app memory-maps so the weights are not copied into the app's memory) and
OUT_DIR/vocab.json.
Usage: python tools/export_model.py OUT_DIR"""
import glob
import json
import os
import shutil
import subprocess
import sys

import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
from transformers import AutoProcessor, Wav2Vec2ForCTC

MODEL = 'facebook/wav2vec2-xlsr-53-espeak-cv-ft'


def main(out):
    os.makedirs(out, exist_ok=True)
    proc = AutoProcessor.from_pretrained(MODEL)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL).eval()
    vocab = {v: k for k, v in proc.tokenizer.get_vocab().items()}
    with open(os.path.join(out, 'vocab.json'), 'w', encoding='utf8') as f:
        json.dump([vocab[i] for i in range(len(vocab))], f, ensure_ascii=False)
    fp32 = os.path.join(out, 'w2v_fp32.onnx')
    torch.onnx.export(model, (torch.randn(1, 16000 * 5),), fp32,
                      input_names=['audio'], output_names=['logits'],
                      dynamic_axes={'audio': {1: 'n'}, 'logits': {1: 't'}},
                      opset_version=17, dynamo=False)
    # 8-bit weights: 4x smaller and a bit faster, same accuracy in our tests
    int8 = os.path.join(out, 'w2v_int8.onnx')
    quantize_dynamic(fp32, int8, weight_type=QuantType.QUInt8)
    os.remove(fp32)
    # mobile format: loads in place from a memory-mapped file
    tmp = os.path.join(out, 'ort_tmp')
    subprocess.run([sys.executable, '-m', 'onnxruntime.tools.convert_onnx_models_to_ort', int8,
                    '--output_dir', tmp, '--optimization_style', 'Fixed'], check=True)
    shutil.move(glob.glob(os.path.join(tmp, '*.ort'))[0], os.path.join(out, 'w2v_int8.ort'))
    shutil.rmtree(tmp)
    os.remove(int8)
    print('done:', os.path.getsize(os.path.join(out, 'w2v_int8.ort')) // 1_000_000, 'MB')


if __name__ == '__main__':
    main(sys.argv[1])
