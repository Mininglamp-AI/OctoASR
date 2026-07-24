# Formula/octoasr.rb (本地测试版)
# 使用方法: brew install --formula homebrew/octoasr-local.rb

class Octoasr < Formula
  desc "本地语音转写服务，基于 MLX，针对 Apple Silicon 优化"
  homepage "https://github.com/octoasr/octoasr"
  url "file:///dev/null"
  sha256 "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  license "MIT"
  version "0.1.0"

  bottle do
    root_url "file:///Users/mlamp/Desktop/asr/octoasr/build/release-v0.1.0"
    sha256 cellar: :any_skip_relocation, arm64_tahoe: "b4cc4ecb26afede6bd3dd6532b39591644e6b1383a5b3885da5cdedbec866f6d"
  end

  depends_on "ffmpeg"
  depends_on :macos => :monterey
  depends_on :arch => :arm64

  def install
    odie "请先运行 ./homebrew/build-bottle.sh 构建 bottle 后再安装"
  end

  def caveats
    <<~EOS
      octoasr 安装完成！

      模型将在首次运行时自动下载（约 1-2 GB）。

      快速开始:
        octoasr start              # 启动服务（首次自动下载模型）
        octoasr transcribe a.wav   # 转写音频
        octoasr model              # 切换 ASR 引擎

      服务管理:
        octoasr start / stop / restart / status
        octoasr logs --stats       # 查看统计
        octoasr doctor             # 环境检查

      模型存储: ~/.octoasr/models/
      服务地址: http://127.0.0.1:8787
    EOS
  end

  service do
    run [opt_bin/"octoasr", "start", "--foreground"]
    keep_alive true
    working_dir var
    log_path var/"log/octoasr.log"
    error_log_path var/"log/octoasr.log"
  end

  test do
    assert_match "0.1.0", shell_output("#{bin}/octoasr --version")
  end
end
