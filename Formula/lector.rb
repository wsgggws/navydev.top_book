class Lector < Formula
  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  version "1.3.12"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.12/lector-macos-arm64.tar.gz"
      sha256 "eff96c7b6df042365658ec6f086ec67430a8520f7ded2945b03cf7237db10faf"
    else
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.12/lector-macos-x86_64.tar.gz"
      sha256 "241eb044897fa88ea7c21ecfbe73f35980d68434ab67ecc4df24a79028b169e4"
    end
  end

  def install
    bin.install "lector"
  end

  test do
    assert_match "lector 1.3.12", shell_output("#{bin}/lector --version")
  end
end
