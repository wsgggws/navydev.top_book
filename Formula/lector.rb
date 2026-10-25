class Lector < Formula
  include Language::Python::Virtualenv

  desc "Read-only terminal client for navydev.top/ebook"
  homepage "https://navydev.top/ebook"
  url "https://github.com/wsgggws/navydev.top_ebook/releases/download/terminal-v1.1.0/lector_tui-1.1.0.tar.gz"
  sha256 "343f5f316a4d99ac2cdc2b38c37f30738a4886fa88bbc0ccf9610384b57327fb"

  depends_on "python@3.12"

  def install
    venv = virtualenv_create(libexec, "python3.12")
    venv.pip_install_and_link buildpath
  end

  test do
    assert_match "lector 1.1.0", shell_output("#{bin}/lector --version")
  end
end
