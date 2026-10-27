class Lector < Formula
  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  version "1.3.13"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.13/lector-macos-arm64.tar.gz"
      sha256 "59dcf96b81d32cbe446edb272a6a77354c8f26e3139212fbe6dc14119d329137"
    else
      url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.3.13/lector-macos-x86_64.tar.gz"
      sha256 "112b6cbdea48d56f99d856c38e172180a996e7ebe43968dbe602fe2fbf06fa4c"
    end
  end

  def install
    # Homebrew stages inside the archive's sole top-level directory.
    # Keep the bootloader and its private _internal runtime together.
    libexec.install Dir["*"]
    bin.install_symlink libexec/"lector"
  end

  test do
    assert_match "lector 1.3.13", shell_output("#{bin}/lector --version")
  end
end
