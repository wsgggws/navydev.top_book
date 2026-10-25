class Lector < Formula
  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  version "1.3.2"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.2/lector-macos-arm64.tar.gz"
      sha256 "802faf7364cd0eb4f9daaae3b8288cc5c1aa44e99f1b35eed2f75f0b5d9e2496"
    else
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.2/lector-macos-x86_64.tar.gz"
      sha256 "4a6fb31b8ee718c0cbd2b57065e767a1c2db67092390294d65f2e4eb75978d5c"
    end
  end

  def install
    bin.install "lector"
  end

  test do
    assert_match "lector 1.3.2", shell_output("#{bin}/lector --version")
  end
end
