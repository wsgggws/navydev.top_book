class Lector < Formula
  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  version "1.3.8"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.8/lector-macos-arm64.tar.gz"
      sha256 "58e703fcf8729de8c7dfc27d1ee0fdb61b850bb5a9af517ed77a4f42fd9a828b"
    else
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.8/lector-macos-x86_64.tar.gz"
      sha256 "83bfd6639e4f2f40488e0fc9dda538d5415e6c3c4b57e89921801a7a2964894a"
    end
  end

  def install
    bin.install "lector"
  end

  test do
    assert_match "lector 1.3.8", shell_output("#{bin}/lector --version")
  end
end
