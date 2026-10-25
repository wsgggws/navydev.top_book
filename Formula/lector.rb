class Lector < Formula
  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  version "1.3.7"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.7/lector-macos-arm64.tar.gz"
      sha256 "bda2e3f984acfcaaba3de59dab2fcf6b038c94a57d087f87ef1253cc80ae210d"
    else
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.7/lector-macos-x86_64.tar.gz"
      sha256 "29702675687aa5a7d9a2c8fb142eb30c73dddb906d02fb5b318d26d9e6f307ce"
    end
  end

  def install
    bin.install "lector"
  end

  test do
    assert_match "lector 1.3.7", shell_output("#{bin}/lector --version")
  end
end
