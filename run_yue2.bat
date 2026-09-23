@echo off
title YuE2 - ComfyUI AI Music Generation
echo =======================================================================
echo  YuE2 Standalone Environment (RTX 4070 Ti 12GB VRAM)
echo  Location: E:\repos\YuE2
echo  PyTorch: 2.14.0+cu126 (DynamicVRAM / System RAM Offload Enabled)
echo  Models:
echo    - yue2_3b_int8_convrot.safetensors (Lower VRAM, 3.96 GB; may run slower)
echo    - yue2_3b_bf16.safetensors (Studio default, 7.80 GB)
echo    - sheetsage2_bf16.safetensors (Audio Encoder, 1.39 GB)
echo =======================================================================

cd /d "%~dp0ComfyUI"
..\venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188 --auto-launch --disable-smart-memory
pause
