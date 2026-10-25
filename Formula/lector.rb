class Lector < Formula
  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  version "1.3.4"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.4/lector-macos-arm64.tar.gz"
      sha256 "1729bfa890c17e26a4a83934072b71f499427fd3bf346f1747ba06bad5accb85"
    else
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.4/lector-macos-x86_64.tar.gz"
      sha256 "7a3ff18b89ddf8fe84704f8792fa31dd51cdc483760ff3adb73f2619b7c7a20d"
    end
  end

  def install
    bin.install "lector"
  end

  test do
    assert_match "lector 1.3.4", shell_output("#{bin}/lector --version")
  end
end
