pkgname=systemd-boot-lifeboat
pkgver=0.0.1
pkgrel=1
pkgdesc=''
arch=('any')
license=('MIT')
depends=('python')
source=(
  'systemd_boot_lifeboat.py'
  'systemd-boot-lifeboat.service'
)

package() {
  install -D -m0755 "${srcdir}/systemd_boot_lifeboat.py" "${pkgdir}/usr/share/systemd-boot-lifeboat/systemd_boot_lifeboat.py"
  install -D -m0644 "${srcdir}/systemd-boot-lifeboat.service" "${pkgdir}/usr/lib/systemd/system/systemd-boot-lifeboat.service"
}

sha256sums=('ddb05e7b40173fdd745a06ccd9aa29ed21e00590849bb780eb2782cd031d70cf'
            '6c1ac4024a45276266161cf1df56e5b6a214539abb8c26e91914e58b730504db')

