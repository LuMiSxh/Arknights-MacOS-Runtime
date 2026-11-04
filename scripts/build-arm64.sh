#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0

# Build an entitlement-free ARM64 runtime for the native-arm64 target.
# The recipe is docs/arm/pipeline.md. This never runs Wine and never starts a game.

set -euo pipefail

repository_root="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$repository_root"

target="native-arm64"
build_root="$repository_root/.build/stages/arm64"
source_root="$build_root/sources"
candidate="$build_root/candidate/Libraries"
capability_manifest="$repository_root/runtime-capabilities.json"

resume=false
prepare_stage="combined"
skipped_patches=()
for argument in "$@"; do
	case "$argument" in
		--resume) resume=true ;;
		--no-patches) prepare_stage="base" ;;
		*)
			echo "error: unknown argument: $argument" >&2
			exit 2
			;;
	esac
done

if [[ "$prepare_stage" == combined ]]; then
	# The arm64-1117 branch has not taken the rebased fullscreen patch yet.
	# Every other family applies; docs/arm/porting.md tracks the rebase.
	skipped_patches=(--skip-patch wine-fullscreen-native-space)
fi

wine_source="$source_root/wine-$target-combined"
dxmt_source="$source_root/dxmt-$target-combined"
fex_source="$source_root/fex-$target-combined"
wine_build="$build_root/wine-build"
wine_staging="$build_root/wine-staging"
fex_install="$build_root/fex-install"
dxmt_install="$build_root/dxmt-install"

llvm_mingw_root="${LLVM_MINGW_ROOT:-$repository_root/.build/toolchains/llvm-mingw}"
llvm15_root="${LLVM_ROOT:-$(brew --prefix llvm@15 2>/dev/null || true)}"

require_command() {
	command -v "$1" >/dev/null || {
		echo "error: required command not found: $1" >&2
		exit 1
	}
}

run_python() {
	uv run --locked --no-dev python "$@"
}

for command in git cmake meson ninja uv bison flex pkg-config codesign vtool brew; do
	require_command "$command"
done
for compiler in arm64ec-w64-mingw32-clang aarch64-w64-mingw32-clang; do
	[[ -x "$llvm_mingw_root/bin/$compiler" ]] || {
		echo "error: $compiler not found; set LLVM_MINGW_ROOT to an llvm-mingw release" >&2
		exit 1
	}
done
[[ -d "$llvm_mingw_root/bin" ]] || {
	echo "error: LLVM_MINGW_ROOT has no bin directory: $llvm_mingw_root" >&2
	exit 1
}
[[ -d "${llvm15_root:?}/lib" ]] || {
	echo "error: set LLVM_ROOT to an LLVM 15 install with lib and include" >&2
	exit 1
}

export PATH="$llvm_mingw_root/bin:$(brew --prefix bison)/bin:$PATH"
export SDKROOT="$(xcrun --show-sdk-path)"
deployment_target="$(run_python -c 'import sys; from scripts.runtime import load_lock; print(load_lock(target=sys.argv[1])["deploymentTarget"])' "$target")"
export MACOSX_DEPLOYMENT_TARGET="$deployment_target"

if [[ -e "$build_root" && "$resume" == false ]]; then
	echo "error: build output already exists: $build_root (use --resume)" >&2
	exit 1
fi
mkdir -p "$source_root" "$candidate"

run_python scripts/runtime.py validate-lock --target "$target"
if [[ -d "$wine_source" && -d "$dxmt_source" && -d "$fex_source" ]]; then
	echo "== Sources present"
else
	prepare_arguments=(prepare "$prepare_stage" --target "$target" --all-sources)
	prepare_arguments+=(--destination-root "$source_root")
	if [[ ${#skipped_patches[@]} -gt 0 ]]; then
		prepare_arguments+=("${skipped_patches[@]}")
	fi
	run_python scripts/runtime.py "${prepare_arguments[@]}"
fi

echo "== Wine"
pkg_config_path=""
include_flags=""
link_flags=""
for package in freetype gnutls vulkan-headers; do
	prefix="$(brew --prefix "$package")"
	pkg_config_path="$prefix/lib/pkgconfig:$pkg_config_path"
	include_flags="$include_flags -I$prefix/include"
	link_flags="$link_flags -L$prefix/lib"
done
export PKG_CONFIG_PATH="$pkg_config_path"
export CFLAGS="-O2 -Wno-error=implicit-function-declaration -Werror=unguarded-availability-new $include_flags"
export LDFLAGS="$link_flags"
export ac_cv_lib_soname_freetype="libfreetype.6.dylib"
export ac_cv_lib_soname_gnutls="libgnutls.30.dylib"
# pipe2 arrives in macOS 27; the deployment target stays at the lock value.
export ac_cv_func_pipe2=no
export CC="ccache /usr/bin/clang -arch arm64"
export CXX="ccache /usr/bin/clang++ -arch arm64"

mkdir -p "$wine_build"
# The arm64 branch reads SONAME_LIBVULKAN in a PE module without a guard, and
# this build configures no Vulkan driver. DXMT talks to Metal and never loads one.
(
	cd "$wine_source"
	run_python -c 'import pathlib; path = pathlib.Path("dlls/win32u/vulkan.c"); text = path.read_text(); anchor = "static void vulkan_init_once(void)"; marker = "#ifndef SONAME_LIBVULKAN"; text = text if marker in text else text.replace(anchor, "#ifndef SONAME_LIBVULKAN\n#define SONAME_LIBVULKAN \"libvulkan.1.dylib\"\n#endif\n\n" + anchor, 1); path.write_text(text)'
)
(
	cd "$wine_build"
	if [[ ! -f Makefile ]]; then
		"$wine_source/configure" \
			--host=aarch64-apple-darwin \
			--enable-archs=arm64ec,aarch64 \
			--disable-tests \
			--without-x --without-wayland --without-oss --without-alsa --without-pulse \
			--without-sane --without-usb --without-v4l2 --without-pcap --without-capi \
			--without-opencl --without-cups \
			--without-ffmpeg --without-gstreamer \
			--prefix=/opt/whiskywine
	fi
	make -j"$(sysctl -n hw.logicalcpu)"
	make install DESTDIR="$wine_staging"
)
wine_install="$wine_staging/opt/whiskywine"

echo "== FEX"
git -C "$fex_source" submodule update --init --recursive
mkdir -p "$fex_install"
for triple in arm64ec-w64-mingw32 aarch64-w64-mingw32; do
	fex_build="$build_root/fex-$triple"
	cmake -S "$fex_source" -B "$fex_build" -G Ninja \
		-DCMAKE_TOOLCHAIN_FILE="$fex_source/Data/CMake/toolchain_mingw.cmake" \
		-DMINGW_TRIPLE="$triple" \
		-DCMAKE_BUILD_TYPE=Release -DENABLE_LTO=FALSE -DBUILD_TESTING=FALSE \
		-DENABLE_OFFLINE_TELEMETRY=FALSE -DTUNE_CPU=none \
		-DCMAKE_INSTALL_PREFIX="$fex_install"
	cmake --build "$fex_build"
	cmake --install "$fex_build"
done
for module in arm64ecfex wow64fex; do
	/usr/bin/clang++ -std=c++20 -O2 -shared -fPIC -arch arm64 \
		-mmacosx-version-min="$deployment_target" \
		-I"$fex_source/Source/Windows/UnixLib" \
		"$fex_source/Source/Windows/UnixLib/FEXUnixLib.cpp" \
		-o "$wine_install/lib/wine/aarch64-unix/lib$module.so"
done

echo "== DXMT"
git -C "$dxmt_source" submodule update --init --recursive
(
	unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS CC CXX
	if [[ ! -f "$build_root/dxmt-build/build.ninja" ]]; then
		meson setup "$build_root/dxmt-build" "$dxmt_source" \
			--cross-file "$dxmt_source/build-arm64ec.txt" \
			-Dnative_llvm_path="$llvm15_root" \
			-Dwine_build_path="$wine_build" \
			--buildtype release --prefix "$dxmt_install" --strip
	fi
	meson compile -C "$build_root/dxmt-build"
	meson install -C "$build_root/dxmt-build"
)

echo "== Assemble"
mkdir -p "$candidate/Wine" "$candidate/DXMT/x64"
cp -R "$wine_install/bin" "$wine_install/lib" "$wine_install/share" "$candidate/Wine/"
loader="$candidate/Wine/lib/wine/aarch64-unix/wine"
[[ -x "$loader" ]] || {
	echo "error: the Wine install has no ARM64 loader: $loader" >&2
	exit 1
}
for name in wine wine64 wineloader; do
	ln -sf ../lib/wine/aarch64-unix/wine "$candidate/Wine/bin/$name"
done
ln -sf wine64 "$candidate/Wine/bin/Arknights"

# macOS clears x18 unless the main executable's SDK is 12.0 or older.
vtool -set-build-version macos "$deployment_target" 12.0 -replace \
	-o "$loader.versioned" "$loader"
mv "$loader.versioned" "$loader"
chmod u+x "$loader"

cp "$fex_install/lib/libarm64ecfex.dll" "$candidate/Wine/lib/wine/aarch64-windows/"
cp "$fex_install/lib/libwow64fex.dll" "$candidate/Wine/lib/wine/aarch64-windows/"
cp "$dxmt_install/aarch64-windows/winemetal.dll" \
	"$candidate/Wine/lib/wine/aarch64-windows/winemetal.dll"
cp "$dxmt_install/aarch64-unix/winemetal.so" \
	"$candidate/Wine/lib/wine/aarch64-unix/winemetal.so"
for library in d3d10core.dll d3d11.dll dxgi.dll; do
	cp "$dxmt_install/aarch64-windows/$library" "$candidate/DXMT/x64/$library"
	printf '\016\037\272\016\000\264\011\315\041\270\001\114\315\041\220\220' |
		dd of="$candidate/DXMT/x64/$library" bs=1 seek=64 conv=notrunc status=none
done
cp "$capability_manifest" "$candidate/"

echo "== Bundled libraries"
library_directory="$candidate/Wine/lib"
queue=""
for prefix in "$(brew --prefix freetype)" "$(brew --prefix gnutls)"; do
	for library in libfreetype.6.dylib libgnutls.30.dylib; do
		[[ -f "$prefix/lib/$library" ]] && queue="$queue $prefix/lib/$library"
	done
done
for binary in "$library_directory"/wine/aarch64-unix/*.so; do
	[[ -f "$binary" ]] || continue
	queue="$queue $(otool -L "$binary" 2>/dev/null | awk '/^\t\/opt\/homebrew\// {print $1}' | tr '\n' ' ')"
done
while [[ -n "$queue" ]]; do
	next=""
	for reference in $queue; do
		name="$(basename "$reference")"
		[[ -e "$library_directory/$name" ]] && continue
		cp -L "$reference" "$library_directory/$name"
		chmod u+w "$library_directory/$name"
		next="$next $(otool -L "$library_directory/$name" 2>/dev/null | awk '/^\t\/opt\/homebrew\// {print $1}' | tr '\n' ' ')"
	done
	queue=""
	for reference in $next; do
		[[ -e "$library_directory/$(basename "$reference")" ]] || queue="$queue $reference"
	done
done

fixup_macho() {
	local binary="$1"
	local relative
	relative="$(run_python -c 'import os,sys; print(os.path.relpath(sys.argv[1], os.path.dirname(sys.argv[2])))' "$library_directory" "$binary")"
	chmod u+w "$binary"
	case "$binary" in
		*.dylib*) install_name_tool -id "@loader_path/$(basename "$binary")" "$binary" 2>/dev/null || true ;;
	esac
	while IFS= read -r reference; do
		install_name_tool -change "$reference" \
			"@loader_path/$relative/$(basename "$reference")" "$binary"
	done < <(otool -L "$binary" 2>/dev/null | awk '/^\t\/opt\/homebrew\// {print $1}')
	codesign --force --sign - "$binary"
}
for binary in "$library_directory"/*.dylib* "$library_directory"/wine/aarch64-unix/*.so; do
	[[ -f "$binary" ]] && fixup_macho "$binary"
done

echo "== Validate"
while IFS= read -r binary; do
	[[ -L "$binary" ]] && continue
	if file -b "$binary" | grep -q "Mach-O"; then
		codesign --force --sign - "$binary"
	fi
done < <(find "$candidate" -type f)

run_python scripts/validate_runtime.py "$candidate" --target "$target" \
	--require-capabilities --require-64-bit-only

archive="$build_root/Arknights-MacOS-Runtime-arm64-canary.tar.gz"
tar -czf "$archive" -C "$build_root/candidate" Libraries
shasum -a 256 "$archive" > "$archive.sha256"
echo "artifact: $archive"
