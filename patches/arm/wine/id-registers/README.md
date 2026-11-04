# Synthesize the ARM64 ID registers on macOS

macOS does not let EL0 read the ID registers.
Wine returned an empty SMBIOS processor block, so FEX read zero features from
`HKLM\Hardware\Description\System\CentralProcessor\0` and hit its own assert in
`FetchHostFeatures`.

Build the registers from the `hw.optional.arm.*` sysctls and the cache line
size.
The patch adds the `__APPLE__` case to `get_core_id_regs_arm64`; Linux keeps its
existing implementation.

Apply time: after the address-space patch, before the prefix is created.
