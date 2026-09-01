#!/usr/bin/env bash
# SPDX-License-Identifier: MPL-2.0

set -euo pipefail

stage="${1:-combined}"
case "$stage" in
	base|audio|cursor|cn|combined) ;;
	*)
		echo "error: expected base, audio, cursor, cn, or combined" >&2
		exit 2
		;;
esac

repository_root="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$repository_root"
build_root="$repository_root/.build"
stage_root="$build_root/stages/$stage"
lock="$repository_root/runtime.lock.json"

require_command() {
	command -v "$1" >/dev/null || {
		echo "error: required command not found: $1" >&2
		exit 1
	}
}

for command in git shasum tar uv; do
	require_command "$command"
done

run_python() {
	uv run --locked --no-dev python "$@"
}

deployment_target="$(run_python -c 'import json,sys; print(json.load(open(sys.argv[1]))["deploymentTarget"])' "$lock")"
nixpkgs_revision="$(run_python -c 'import json,sys; print(json.load(open(sys.argv[1]))["build"]["nixpkgsCommit"])' "$lock")"
nixpkgs="github:NixOS/nixpkgs/$nixpkgs_revision"

export MACOSX_DEPLOYMENT_TARGET="$deployment_target"

if [[ -e "$stage_root" ]]; then
	echo "error: stage output already exists: $stage_root" >&2
	exit 1
fi

run_python "$repository_root/scripts/runtime.py" validate-lock
base_archive="$(run_python "$repository_root/scripts/runtime.py" fetch-base)"
mkdir -p "$stage_root/base" "$stage_root/candidate"
tar -xzf "$base_archive" -C "$stage_root/base"
if ! cp -cR "$stage_root/base/Libraries" "$stage_root/candidate/Libraries" 2>/dev/null; then
	cp -R "$stage_root/base/Libraries" "$stage_root/candidate/Libraries"
fi
candidate="$stage_root/candidate/Libraries"

if [[ "$stage" == base ]]; then
	run_python "$repository_root/scripts/validate_runtime.py" "$candidate" --baseline "$stage_root/base/Libraries"
	tar -czf "$stage_root/Arknights-MacOS-Runtime-$stage.tar.gz" -C "$stage_root/candidate" Libraries
	(cd "$stage_root" && shasum -a 256 "Arknights-MacOS-Runtime-$stage.tar.gz" > "Arknights-MacOS-Runtime-$stage.tar.gz.sha256")
	(cd "$stage_root" && shasum -a 256 -c "Arknights-MacOS-Runtime-$stage.tar.gz.sha256")
	exit 0
fi

require_command nix

source_root="$stage_root/sources"
if [[ "$stage" == cursor ]]; then
	run_python "$repository_root/scripts/runtime.py" prepare cursor --destination-root "$source_root"
	run_python "$repository_root/scripts/runtime.py" prepare base --destination-root "$source_root"
else
	run_python "$repository_root/scripts/runtime.py" prepare "$stage" --destination-root "$source_root"
fi

wine_source="$source_root/wine-$stage"
if [[ "$stage" == cursor ]]; then
	wine_source="$source_root/wine-base"
fi

require_command clang
require_command make
require_command x86_64-w64-mingw32-gcc
require_command i686-w64-mingw32-gcc

nix_tools="$(nix build --no-link --print-out-paths \
	"$nixpkgs#bison" "$nixpkgs#flex" "$nixpkgs#pkg-config")"
nix_tool_path=""
for output in $nix_tools; do
	nix_tool_path="$output/bin:$nix_tool_path"
done

nix_outputs=""
for package in freetype gnutls libpng zlib brotli bzip2 nettle libtasn1 libidn2 p11-kit libunistring gmp vulkan-headers ffmpeg-headless glib orc gst_all_1.gstreamer gst_all_1.gst-plugins-base gst_all_1.gst-plugins-good gst_all_1.gst-plugins-bad gst_all_1.gst-libav; do
	for output_name in dev out lib; do
		if output="$(nix build --no-link --print-out-paths "$nixpkgs#legacyPackages.x86_64-darwin.$package.$output_name" 2>/dev/null)"; then
			nix_outputs="$nix_outputs $output"
		fi
	done
done

pkg_config_path=""
include_flags=""
link_flags=""
for output in $nix_outputs; do
	[[ -d "$output/lib/pkgconfig" ]] && pkg_config_path="$output/lib/pkgconfig:$pkg_config_path"
	[[ -d "$output/include" ]] && include_flags="$include_flags -I$output/include"
	[[ -d "$output/lib" ]] && link_flags="$link_flags -L$output/lib"
done

export PATH="$nix_tool_path:$PATH"
SDKROOT="$(xcrun --show-sdk-path)"
export SDKROOT
export CC="ccache /usr/bin/clang -arch x86_64"
export CXX="ccache /usr/bin/clang++ -arch x86_64"
export PKG_CONFIG_PATH="$pkg_config_path"
export CFLAGS="-O2 -Wno-error=implicit-function-declaration -Werror=unguarded-availability-new $include_flags"
export CROSSCFLAGS="-O2"
export LDFLAGS="$link_flags"
export ac_cv_func_pipe2=no
export ac_cv_lib_soname_freetype="libfreetype.6.dylib"
export ac_cv_lib_soname_gnutls="libgnutls.30.dylib"
export ac_cv_lib_soname_MoltenVK="libMoltenVK.dylib"

llvm_path=""
if [[ "$stage" == cursor || "$stage" == combined ]]; then
	llvm_attribute="$nixpkgs#legacyPackages.x86_64-darwin.llvmPackages_15.llvm"
	llvm_dev="$(nix build --no-link --print-out-paths "$llvm_attribute.dev")"
	llvm_lib="$(nix build --no-link --print-out-paths "$llvm_attribute.lib")"
	[[ -d "$llvm_dev/include" ]] || {
		echo "error: LLVM development output has no include directory: $llvm_dev" >&2
		exit 1
	}
	[[ -d "$llvm_lib/lib" ]] || {
		echo "error: LLVM library output has no lib directory: $llvm_lib" >&2
		exit 1
	}
	llvm_path="$stage_root/llvm-native"
	mkdir -p "$llvm_path"
	ln -s "$llvm_dev/include" "$llvm_path/include"
	ln -s "$llvm_lib/lib" "$llvm_path/lib"
fi

wine_build="$stage_root/wine-build"
mkdir -p "$wine_build"
(
	cd "$wine_build"
	"$wine_source/configure" \
		--host=x86_64-apple-darwin24 \
		--enable-archs=i386,x86_64 \
		--disable-tests \
		--without-x --without-wayland --without-oss --without-alsa --without-pulse \
		--without-sane --without-usb --without-v4l2 --without-pcap --without-capi \
		--without-opencl --without-cups \
		--prefix=/opt/whiskywine
	grep -q '^#define HAVE_FFMPEG 1' include/config.h
	grep -qE '^GSTREAMER_LIBS *= *.+' Makefile
	make -j"$(sysctl -n hw.logicalcpu)"
)

if [[ "$stage" == audio || "$stage" == cn || "$stage" == combined ]]; then
	staging="$stage_root/wine-staging"
	make -C "$wine_build" -j"$(sysctl -n hw.logicalcpu)" install-lib DESTDIR="$staging"
	wine_install="$staging/opt/whiskywine"
	patched_machos=()

	overlay_wine_file() {
		local relative="$1"
		[[ -f "$wine_install/$relative" ]] || {
			echo "error: patched Wine output is missing: $relative" >&2
			exit 1
		}
		cp "$wine_install/$relative" "$candidate/Wine/$relative"
	}

	if [[ "$stage" == audio || "$stage" == combined ]]; then
		overlay_wine_file lib/wine/x86_64-unix/winecoreaudio.so
		patched_machos+=("$candidate/Wine/lib/wine/x86_64-unix/winecoreaudio.so")
	fi
	if [[ "$stage" == cn || "$stage" == combined ]]; then
		overlay_wine_file lib/wine/x86_64-unix/ntdll.so
		patched_machos+=("$candidate/Wine/lib/wine/x86_64-unix/ntdll.so")
		overlay_wine_file lib/wine/x86_64-windows/kernel32.dll
		overlay_wine_file lib/wine/x86_64-windows/ntoskrnl.exe
		overlay_wine_file lib/wine/i386-windows/ntoskrnl.exe
		x86_64-w64-mingw32-strip --strip-debug \
			"$candidate/Wine/lib/wine/x86_64-windows/kernel32.dll" \
			"$candidate/Wine/lib/wine/x86_64-windows/ntoskrnl.exe"
		i686-w64-mingw32-strip --strip-debug \
			"$candidate/Wine/lib/wine/i386-windows/ntoskrnl.exe"
	fi

	for binary in "${patched_machos[@]}"; do
		while IFS= read -r reference; do
			dependency="$candidate/Wine/lib/$(basename "$reference")"
			[[ -f "$dependency" ]] || {
				echo "error: patched Wine binary needs an unbundled dependency: $reference" >&2
				exit 1
			}
			install_name_tool -change "$reference" "@rpath/$(basename "$reference")" "$binary"
		done < <(otool -L "$binary" | awk '/\/nix\/store\// {print $1}')
		if ! otool -l "$binary" | awk '$1 == "path" {print $2}' | grep -Fxq '@loader_path/../../'; then
			install_name_tool -add_rpath '@loader_path/../../' "$binary"
		fi
		codesign --force --sign - "$binary"
	done
fi

if [[ "$stage" == cursor || "$stage" == combined ]]; then
	require_command meson
	require_command ninja
	dxmt_source="$source_root/dxmt-$stage"
	git -C "$dxmt_source" submodule update --init --recursive
	dxmt_install="$stage_root/dxmt-install"
	(
		unset CFLAGS CXXFLAGS CPPFLAGS CROSSCFLAGS LDFLAGS
		meson setup \
			--cross-file "$dxmt_source/build-win64.txt" \
			-Dnative_llvm_path="$llvm_path" \
			-Dwine_build_path="$wine_build" \
			--buildtype release --prefix "$dxmt_install" --strip \
			"$stage_root/dxmt-build64" "$dxmt_source"
		meson compile -C "$stage_root/dxmt-build64"
		meson install -C "$stage_root/dxmt-build64"
		meson setup \
			--cross-file "$dxmt_source/build-win32.txt" \
			-Dnative_llvm_path="$llvm_path" \
			-Dwine_build_path="$wine_build" \
			--buildtype release --prefix "$dxmt_install" --strip \
			"$stage_root/dxmt-build32" "$dxmt_source"
		meson compile -C "$stage_root/dxmt-build32"
		meson install -C "$stage_root/dxmt-build32"
	)

	for library in d3d10core.dll d3d11.dll dxgi.dll winemetal.dll; do
		cp "$dxmt_install/x86_64-windows/$library" "$candidate/DXMT/x64/$library"
		cp "$dxmt_install/i386-windows/$library" "$candidate/DXMT/x32/$library"
	done
	cp "$dxmt_install/x86_64-windows/winemetal.dll" "$candidate/Wine/lib/wine/x86_64-windows/winemetal.dll"
	cp "$dxmt_install/x86_64-unix/winemetal.so" "$candidate/Wine/lib/wine/x86_64-unix/winemetal.so"
	codesign --force --sign - "$candidate/Wine/lib/wine/x86_64-unix/winemetal.so"

	for architecture in x64 x32; do
		for library in d3d10core.dll d3d11.dll dxgi.dll; do
			printf '\016\037\272\016\000\264\011\315\041\270\001\114\315\041\220\220' |
				dd of="$candidate/DXMT/$architecture/$library" bs=1 seek=64 conv=notrunc status=none
		done
	done
fi

run_python "$repository_root/scripts/validate_runtime.py" "$candidate" --baseline "$stage_root/base/Libraries"
tar -czf "$stage_root/Arknights-MacOS-Runtime-$stage.tar.gz" -C "$stage_root/candidate" Libraries
(cd "$stage_root" && shasum -a 256 "Arknights-MacOS-Runtime-$stage.tar.gz" > "Arknights-MacOS-Runtime-$stage.tar.gz.sha256")
(cd "$stage_root" && shasum -a 256 -c "Arknights-MacOS-Runtime-$stage.tar.gz.sha256")
