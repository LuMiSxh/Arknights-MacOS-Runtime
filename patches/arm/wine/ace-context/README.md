# Carry EFlags AF and DF through ARM64EC contexts

ARM64EC contexts map the x86 flags to NZCV. AF and DF have no NZCV equivalent, so Wine dropped
them. ACE reads both after a context switch.

Keep the flags in RES0 CPSR bits 16 and 17. The hardware never reads those bits. The patch changes
`eflags_to_cpsr` and `cpsr_to_eflags` in `dlls/ntdll/unwind.h`.

Apply it to the `native-arm64` target only.
