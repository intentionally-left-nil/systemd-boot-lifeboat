# Systemd-boot-lifeboat

Automatically backup your bootloader entries to a backup configuration, for easy restoration.

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
makepkg -si -p PKGBUILD.dev
sudo systemctl enable systemd-boot-lifeboat.service
```

# Manual Installation

1. Copy [systemd_boot_lifeboat.py](/systemd_boot_lifeboat.py) to your system, and make it executable.
1. Enable the script to run once per-boot (with root permissions)

# Configuration options

The main flags to change are the `--esp-path` if your config is not mounted at /efi
and `--default-config-path` to hardcode the name of the config you want backed up (e.g. `/efi/loader/entries/arch.conf`)

If you are using the provided `systemd-boot-lifeboat.service`, you can customize these options by creating a drop-in file.
Simply run `sudo systemctl edit systemd-boot-lifeboat.service` and add the following to your override.conf:

```
[Service]
ExecStart=
ExecStart=/usr/share/systemd-boot-lifeboat/systemd_boot_lifeboat.py --your-flags-here
```

You need the `ExecStart=` to clear out the service's default ExecStart

```
usage: systemd_boot_lifeboat.py [-h] [-n MAX_LIFEBOATS] [-e ESP_PATH] [-b BOOT_PATH] [--default-sort-key DEFAULT_SORT_KEY]
                                [--default-version DEFAULT_VERSION] [-c DEFAULT_CONFIG_PATH] [--dry-run]

Clone the boot entry if it has changed

options:
  -h, --help            show this help message and exit
  -n MAX_LIFEBOATS, --max-lifeboats MAX_LIFEBOATS
  -e ESP_PATH, --esp-path ESP_PATH
                        Directory of the efi system partition (default: /efi)
  -b BOOT_PATH, --boot-path BOOT_PATH
                        Directory of the efi system partition (default: None)
  --default-sort-key DEFAULT_SORT_KEY
                        Default sort key to use, if not present (default: linux)
  --default-version DEFAULT_VERSION
                        Default sort key to use, if not present (default: uname -a)
  -c DEFAULT_CONFIG_PATH, --default-config-path DEFAULT_CONFIG_PATH
                        Fully qualified location to the conf file to use as a template for creating new lifeboats (default: None)
  --dry-run             Print what would actually happen, but take no action (default: False)
```

By default, systemd-boot-lifeboat looks in the `/efi` directory for your ESP, and keeps the previous two entries backed up. You can change this by passing in --efi and --max_backups to the python script. To make this change, you need to type `systemctl edit systemd-boot-lifeboat.service` and modify the command line as appropriate

# Development

1. Clone the repository
1. ln -s $PWD/pre-commit $PWD/.git/hooks/
1. Run the unit tests `sudo python -m unittest -v `

The unit tests have to be run as root, unfortunately, due to the extensive use of chroot.
