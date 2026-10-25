class Lector < Formula
  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  version "1.3.11"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.11/lector-macos-arm64.tar.gz"
      sha256 "7a2ebd70b5e8687298eb15dec789fea188423b004000a0032bfe22e4267a3abc"
    else
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.11/lector-macos-x86_64.tar.gz"
      sha256 "fbb87c9e016b4f94ef3b442c2c465cfde3c519f55bf8090e8e1cec8f78b6136c"
    end
  end

  def install
    bin.install "lector"
  end

  test do
    assert_match "lector 1.3.11", shell_output("#{bin}/lector --version")
  end
end
