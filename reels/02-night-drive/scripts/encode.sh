#!/usr/bin/env bash
# Mux build/frames + audio into the deliverables.
#   halfsecond_reel_02.mp4           1080x1920 30fps, music + SFX (TikTok / Reels / Shorts)
#   halfsecond_reel_02_no_music.mp4  same picture, SFX only (add a trending sound in-app)
#   halfsecond_reel_02_4k.mp4        2160x3840 upscale for YouTube Shorts (gets the higher-bitrate encode)
#   cover.jpg                        grid / thumbnail cover
set -euo pipefail
cd "$(dirname "$0")/.."
B=build
FR="$B/frames/%04d.png"

loud() {  # two-pass loudness normalisation to -11 LUFS / -1 dBTP
  local in=$1 out=$2
  local js
  js=$(ffmpeg -hide_banner -i "$in" -af loudnorm=I=-11:TP=-1.0:LRA=9:print_format=json -f null - 2>&1 | sed -n '/^{/,/^}/p')
  local mi mtp mlra mth off
  mi=$(echo "$js" | python3 -c "import json,sys;print(json.load(sys.stdin)['input_i'])")
  mtp=$(echo "$js" | python3 -c "import json,sys;print(json.load(sys.stdin)['input_tp'])")
  mlra=$(echo "$js" | python3 -c "import json,sys;print(json.load(sys.stdin)['input_lra'])")
  mth=$(echo "$js" | python3 -c "import json,sys;print(json.load(sys.stdin)['input_thresh'])")
  off=$(echo "$js" | python3 -c "import json,sys;print(json.load(sys.stdin)['target_offset'])")
  ffmpeg -v error -y -i "$in" -af "loudnorm=I=-11:TP=-1.0:LRA=9:measured_I=$mi:measured_TP=$mtp:measured_LRA=$mlra:measured_thresh=$mth:offset=$off:linear=true,aresample=48000" \
    -ar 48000 "$out"
}

loud audio/mix.wav "$B/mix_norm.wav"
loud audio/sfx.wav "$B/sfx_norm.wav"

X264=(-c:v libx264 -preset slow -crf 16 -maxrate 30M -bufsize 60M -pix_fmt yuv420p -profile:v high -level 4.2
      -x264-params "keyint=60:min-keyint=30:aq-mode=3:psy-rd=1.0,0.15:deblock=-1,-1"
      -color_primaries bt709 -color_trc bt709 -colorspace bt709 -movflags +faststart)

ffmpeg -v error -y -framerate 30 -i "$FR" -i "$B/mix_norm.wav" "${X264[@]}" \
  -c:a aac -b:a 320k -ar 48000 -shortest "$B/halfsecond_reel_02.mp4"
# same video stream, SFX-only audio
ffmpeg -v error -y -i "$B/halfsecond_reel_02.mp4" -i "$B/sfx_norm.wav" -map 0:v -map 1:a -c:v copy \
  -c:a aac -b:a 320k -ar 48000 -shortest -movflags +faststart "$B/halfsecond_reel_02_no_music.mp4"
ffmpeg -v error -y -framerate 30 -i "$FR" -i "$B/mix_norm.wav" \
  -vf "scale=2160:3840:flags=lanczos,unsharp=5:5:0.35:5:5:0.0" \
  -c:v libx264 -preset slow -crf 18 -maxrate 40M -bufsize 80M -pix_fmt yuv420p -profile:v high -level 5.2 \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 -movflags +faststart \
  -c:a aac -b:a 320k -ar 48000 -shortest "$B/halfsecond_reel_02_4k.mp4"
ffmpeg -v error -y -i "$B/frames/0420.png" -q:v 2 "$B/cover.jpg"
rm -f "$B/mix_norm.wav" "$B/sfx_norm.wav"
ls -la "$B"/*.mp4 "$B"/cover.jpg
