class Lector < Formula
  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  version "1.3.5"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.5/lector-macos-arm64.tar.gz"
      sha256 "7707fd6568cccbf1aafcc8f3a22fe5bdfcefed7bd5bf2730e25aa7780926f69e"
    else
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.5/lector-macos-x86_64.tar.gz"
      sha256 "d165a50bc3bcf26b2a3f7e645d728e71a56a22e3953839056efae0e5bb177730"
    end
  end

  def install
    bin.install "lector"
  end

  test do
    assert_match "lector 1.3.5", shell_output("#{bin}/lector --version")
  end
end
