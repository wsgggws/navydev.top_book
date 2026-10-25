class Lector < Formula
  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  version "1.2.1"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.2.1/lector-macos-arm64.tar.gz"
      sha256 "e07a9697957cace9cd19db264993e844f7e1a0c9728342a873179ee35a94a031"
    else
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.2.1/lector-macos-x86_64.tar.gz"
      sha256 "1778aa596c2192a692842e27ae8e8acfeb4e84ffdb477d4375b91137ecf5ec7d"
    end
  end

  def install
    bin.install "lector"
  end

  test do
    assert_match "lector 1.2.1", shell_output("#{bin}/lector --version")
  end
end
