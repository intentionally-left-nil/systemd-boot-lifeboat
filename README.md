# Systemd-boot-lifeboat

Automatically backup your bootloader entries to a backup configuration, for easy restoration.

Note: This only currently works for unified kernel images (using efi= in your loader). Support for linux= coming later :)

# Example

```
#> sudo ./systemd_boot_lifeboat.py --esp=/efi
Copying /EFI/Arch/linux-signed.efi to /EFI/Arch/lifeboat_1660426707_linux-signed.efi
Created boot entry: lifeboat_1660426707_arch_signed.conf
#> sudo ./systemd_boot_lifeboat.py --esp=/efi
arch_signed.conf is already backed up to lifeboat_1660426707_arch_signed.conf
 Nothing to do
#> sudo mkinitcpio -P; sudo sbupdate
==> Building image from preset: /etc/mkinitcpio.d/linux.preset: 'default'
#> sudo ./systemd_boot_lifeboat.py --esp=/efi
Copying /EFI/Arch/linux-signed.efi to /EFI/Arch/lifeboat_1660426748_linux-signed.efi
Created boot entry: lifeboat_1660426748_arch_signed.conf
```

# Requirements

1. Use [systemd-boot](https://wiki.archlinux.org/title/Systemd-boot) as your bootloader
1. Have your efi system partition (ESP) mounted somewhere (typically to /efi)
1. Have enough room on your ESP to store backups

# Installation (Arch-derived OS)

```sh
git clone https://github.com/intentionally-left-nil/systemd-boot-lifeboat.git
cd systemd-boot-lifeboat
makepkg -si
sudo systemctl enable systemd-boot-lifeboat.service
```

# Manual Installation

1. Copy [systemd_boot_lifeboat.py](/systemd_boot_lifeboat.py) to your system, and make it executable.
1. Enable the script to run once per-boot (with root permissions)

# Configuration options

By default, systemd-boot-lifeboat looks in the `/efi` directory for your ESP, and keeps the previous two entries backed up. You can change this by passing in --efi and --max_backups to the python script. To make this change, you need to type `systemctl edit systemd-boot-lifeboat.service` and modify the command line as appropriate

# Development

1. Clone the repository
1. ln -s $PWD/pre-commit $PWD/.git/hooks/
1. Run the unit tests `python -m unittest -v `
