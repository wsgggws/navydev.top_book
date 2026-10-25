class Lector < Formula
  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  version "1.3.0"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.0/lector-macos-arm64.tar.gz"
      sha256 "1b95f5e6b7f5ec54c365f94c62223d7fa0d69a78178a22f19ec94fea32f22369"
    else
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.0/lector-macos-x86_64.tar.gz"
      sha256 "b671db6a7ebe6653db5a26239301dc0514b8f3c196f5c1edb52d1b2a98d8f2a8"
    end
  end

  def install
    bin.install "lector"
  end

  test do
    assert_match "lector 1.3.0", shell_output("#{bin}/lector --version")
  end
end
