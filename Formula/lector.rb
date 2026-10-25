class Lector < Formula
  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  version "1.2.0"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.2.0/lector-macos-arm64.tar.gz"
      sha256 "ace0ca00be9ecf42d9fb9f9fa050fcf3fdbbb2948901183fa9e061855188e3e8"
    else
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.2.0/lector-macos-x86_64.tar.gz"
      sha256 "d222918a82f5e957fdfd3b807b15c4ca4aec8455729dc00411778c1af076469a"
    end
  end

  def install
    bin.install "lector"
  end

  test do
    assert_match "lector 1.2.0", shell_output("#{bin}/lector --version")
  end
end
