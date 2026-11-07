Output assets/demo.gif
Set Shell zsh
Set FontSize 15
Set Width 1200
Set Height 720
Set Padding 16
Set TypingSpeed 45ms
Set Theme "Catppuccin Mocha"
Hide
Type "rm -rf /tmp/minu-demo && mkdir -p /tmp/minu-demo && cd /tmp/minu-demo && clear" Enter
Show
Type "git clone -q https://github.com/deepseek-ai/deepinfer && cd deepinfer" Sleep 300ms Enter
Sleep 3s
Type "minu --hf LiquidAI/LFM3-1.7B-GGUF -y" Sleep 300ms Enter
Wait+Screen@60s /model: LFM3/
Sleep 1s
Type "read the README and summarize what this repo is" Sleep 400ms Enter
Sleep 8s
Wait+Screen@120s /tok\/s · auto on +\^o/
Sleep 6s
