class Lector < Formula
  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  version "1.3.3"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.3/lector-macos-arm64.tar.gz"
      sha256 "9fb2f51afbc2f4a0a2582ab7770b25eb59f3df7165cb21a0f3a8c9166f5f5d06"
    else
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.3/lector-macos-x86_64.tar.gz"
      sha256 "2eaec2c295cbcf2ea93b0baf3595f8af04968ab9e20b5585c84761a7bd868ff9"
    end
  end

  def install
    bin.install "lector"
  end

  test do
    assert_match "lector 1.3.3", shell_output("#{bin}/lector --version")
  end
end
