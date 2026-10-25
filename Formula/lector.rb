class Lector < Formula
  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  version "1.3.1"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.1/lector-macos-arm64.tar.gz"
      sha256 "050a710d37bad8fd76ba5e323e3faff763a8c58e73550b126abc9032815579b6"
    else
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.1/lector-macos-x86_64.tar.gz"
      sha256 "05734b8b7cacee89cc0eecc9314df542529ca58a08fcd04ff9bf76dded77c060"
    end
  end

  def install
    bin.install "lector"
  end

  test do
    assert_match "lector 1.3.1", shell_output("#{bin}/lector --version")
  end
end
