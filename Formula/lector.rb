class Lector < Formula
  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  version "1.3.6"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.6/lector-macos-arm64.tar.gz"
      sha256 "d6d3974822e3bb75b96ee42e9fb0b74f0586ba519257f52f25369f02d9aa9be2"
    else
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.6/lector-macos-x86_64.tar.gz"
      sha256 "1e50a2399625e175e41e64d03d758ab1cb83c7575fd018521405e0ddaa3412e3"
    end
  end

  def install
    bin.install "lector"
  end

  test do
    assert_match "lector 1.3.6", shell_output("#{bin}/lector --version")
  end
end
