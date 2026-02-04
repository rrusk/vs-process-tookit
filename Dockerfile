FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# STEP 1: Core Build Tools
RUN apt-get update && apt-get install -y \
    wget tar git build-essential pkg-config \
    autoconf automake libtool \
    && rm -rf /var/lib/apt/lists/*

# STEP 2: Clone Code - PINNED VERSION (Confirmed FFmpeg 4.4 Compatible)
RUN set -e && \
    git clone --recursive https://github.com/HomeOfAviSynthPlusEvolution/L-SMASH-Works.git /tmp/lsw && \
    cd /tmp/lsw && \
    # Dynamically find the commit from May 2022 to ensure FFmpeg 4 compatibility
    git checkout $(git rev-list -n 1 --before="2022-05-01" master) && \
    git submodule update --init --recursive

# STEP 3: Build Custom l-smash (Vimeo Fork)
RUN set -e && cd /tmp && git clone https://github.com/vimeo/l-smash.git && cd l-smash && \
    gcc -O2 -fPIC -c /tmp/lsw/obuparse/obuparse.c -I/tmp/lsw/obuparse -o obuparse.o && \
    ar rcs libobuparse.a obuparse.o && \
    ./configure --prefix=/usr --enable-shared --extra-cflags="-I/tmp/lsw/obuparse" --extra-ldflags="-L." --extra-libs="-lobuparse" && \
    make -j$(nproc) && make install && ldconfig

# STEP 4: System Dependencies and PPAs
# We install 'vapoursynth' which provides the library and Python module in one go.
RUN set -e && apt-get update && apt-get install -y software-properties-common && \
    add-apt-repository ppa:savoury1/backports -y && \
    add-apt-repository ppa:savoury1/multimedia -y && \
    add-apt-repository ppa:savoury1/ffmpeg4 -y && \
    add-apt-repository ppa:savoury1/vapoursynth -y && \
    apt-get update && apt-get install -y \
    python3-pip meson ninja-build yasm nasm libzimg-dev libxxhash-dev \
    vapoursynth libvapoursynth-dev libfftw3-dev \
    libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
    libswresample-dev \
    libffms2-5 ffmsindex && \
    rm -rf /var/lib/apt/lists/*

# STEP 5: Build L-SMASH Works Plugin
RUN set -e && cd /tmp/lsw/VapourSynth && \
    PKG_CONFIG_PATH=/usr/lib/pkgconfig:/usr/local/lib/pkgconfig meson build --buildtype=release && \
    ninja -C build && \
    mkdir -p /usr/lib/x86_64-linux-gnu/vapoursynth && \
    find build -name "libvslsmashsource.so" -exec cp -v {} /usr/lib/x86_64-linux-gnu/vapoursynth/lsmas.so \;

# STEP 6: Build fmtconv
RUN set -e && \
    git clone https://gitlab.com/EleonoreMizo/fmtconv.git /tmp/fmtconv && \
    cd /tmp/fmtconv/build/unix && \
    ./autogen.sh && \
    ./configure --prefix=/usr && \
    make -j$(nproc) && \
    make install && \
    mkdir -p /usr/lib/x86_64-linux-gnu/vapoursynth && \
    find /usr/lib /usr/local/lib -name "libfmtconv.so*" -type f -exec cp -v {} /usr/lib/x86_64-linux-gnu/vapoursynth/libfmtconv.so \;

# STEP 7: Build MVTools, NNEDI3, TemporalSoften2 (focus2), and Miscellaneous Filters
RUN set -e && \
    wget https://codeload.github.com/dubhater/vapoursynth-mvtools/tar.gz/refs/heads/master -O /tmp/mvtools.tar.gz && \
    wget https://codeload.github.com/dubhater/vapoursynth-nnedi3/tar.gz/refs/heads/master -O /tmp/nnedi3.tar.gz && \
    wget https://codeload.github.com/dubhater/vapoursynth-temporalsoften2/tar.gz/refs/heads/master -O /tmp/temporalsoften2.tar.gz && \
    wget https://codeload.github.com/vapoursynth/vs-miscfilters-obsolete/tar.gz/refs/heads/master -O /tmp/miscfilters.tar.gz && \
    mkdir -p /tmp/mv_check /tmp/nn_check /tmp/ts2_check /tmp/misc_check && \
    tar -xzf /tmp/mvtools.tar.gz -C /tmp/mv_check --strip-components=1 && \
    tar -xzf /tmp/nnedi3.tar.gz -C /tmp/nn_check --strip-components=1 && \
    tar -xzf /tmp/temporalsoften2.tar.gz -C /tmp/ts2_check --strip-components=1 && \
    tar -xzf /tmp/miscfilters.tar.gz -C /tmp/misc_check --strip-components=1 && \
    # FAIL-FAST: Check which build system miscfilters uses
    echo "Checking miscfilters build system..." && \
    ls -la /tmp/misc_check/ && \
    if [ -f /tmp/misc_check/meson.build ]; then \
        echo "Found meson.build"; \
    elif [ -f /tmp/misc_check/Makefile ]; then \
        echo "Found Makefile"; \
    elif [ -f /tmp/misc_check/configure.ac ] || [ -f /tmp/misc_check/autogen.sh ]; then \
        echo "Found autotools"; \
    else \
        echo "ERROR: Cannot determine build system for miscfilters!" && \
        exit 1; \
    fi && \
    # Build MVTools (meson)
    cd /tmp/mv_check && meson build && ninja -C build && \
    find . -name "libmvtools.so" -exec cp -v {} /usr/lib/x86_64-linux-gnu/vapoursynth/ \; && \
    # Build NNEDI3 (autotools) - need make install to get weights file!
    cd /tmp/nn_check && ./autogen.sh && ./configure --prefix=/usr && make -j$(nproc) && make install && \
    find /usr/lib -name "libnnedi3.so*" -type f -exec cp -v {} /usr/lib/x86_64-linux-gnu/vapoursynth/libnnedi3.so \; && \
    # Build TemporalSoften2 (meson - NOT autotools!)
    cd /tmp/ts2_check && meson build && ninja -C build && \
    find build -name "libtemporalsoften2.so" -exec cp -v {} /usr/lib/x86_64-linux-gnu/vapoursynth/ \; && \
    # Build Miscellaneous Filters (meson)
    cd /tmp/misc_check && meson build && ninja -C build && \
    find build -name "libmiscfilters.so" -exec cp -v {} /usr/lib/x86_64-linux-gnu/vapoursynth/ \;

# STEP 7.5: Build FFT3DFilter
RUN set -e && \
    git clone https://github.com/myrsloik/VapourSynth-FFT3DFilter.git /tmp/fft3d_check && \
    cd /tmp/fft3d_check && \
    if [ -f meson.build ]; then \
        echo "Found meson.build"; \
        meson build && ninja -C build && \
        find build -name "libfft3dfilter.so" -exec cp -v {} /usr/lib/x86_64-linux-gnu/vapoursynth/ \; ; \
    elif [ -f autogen.sh ]; then \
        echo "Found autotools"; \
        ./autogen.sh && ./configure --prefix=/usr && make -j$(nproc) && \
        find . -name "libfft3dfilter.so" -exec cp -v {} /usr/lib/x86_64-linux-gnu/vapoursynth/ \; ; \
    fi && \
    rm -rf /tmp/fft3d_check

# STEP 7.6: Build znedi3 (Required for QTGMC)
RUN set -e && \
    git clone --recursive https://github.com/sekrit-twc/znedi3.git /tmp/znedi3 && \
    cd /tmp/znedi3 && \
    make -j$(nproc) X86=1 && \
    mkdir -p /usr/lib/x86_64-linux-gnu/vapoursynth && \
    cp -v vsznedi3.so /usr/lib/x86_64-linux-gnu/vapoursynth/libznedi3.so && \
    cp -v nnedi3_weights.bin /usr/lib/x86_64-linux-gnu/vapoursynth/ && \
    rm -rf /tmp/znedi3

# STEP 7.7: Build eedi3m (Required for QTGMC 'Very Slow' preset)
RUN set -e && \
    git clone https://github.com/HomeOfVapourSynthEvolution/VapourSynth-EEDI3.git /tmp/eedi3m && \
    cd /tmp/eedi3m && \
    # BUGFIX: Patch std::max_align_t to max_align_t for GCC 11 compatibility
    sed -i 's/std::max_align_t/max_align_t/g' EEDI3/EEDI3.cpp && \
    # Standard Meson build for high-performance C++ [cite: 5]
    meson setup build --buildtype release && \
    ninja -C build && \
    mkdir -p /usr/lib/x86_64-linux-gnu/vapoursynth && \
    # The plugin namespace 'eedi3m' is provided by libeedi3m.so
    cp -v build/libeedi3m.so /usr/lib/x86_64-linux-gnu/vapoursynth/ && \
    rm -rf /tmp/eedi3m

# STEP 7.8: Build DePan (Required for Stabilization)
RUN set -e && \
    git clone https://github.com/Vapoursynth-Plugins-Gitify/DePan.git /tmp/depan && \
    cd /tmp/depan && \
    # Fix permission for the configure script
    chmod +x configure && \
    make -j$(nproc) && \
    mkdir -p /usr/lib/x86_64-linux-gnu/vapoursynth && \
    cp -v libdepan.so /usr/lib/x86_64-linux-gnu/vapoursynth/ && \
    rm -rf /tmp/depan

# STEP 7.9: Build TDM (Required for Combing Detection)
RUN set -e && apt-get update && apt-get install -y cmake && \
    git clone https://github.com/pinterf/TIVTC.git /tmp/tivtc && \
    # The project root for CMake is TIVTC/src
    cd /tmp/tivtc/src && \
    cmake -B build -S . && \
    cmake --build build -j$(nproc) && \
    mkdir -p /usr/lib/x86_64-linux-gnu/vapoursynth && \
    # Use find to locate the libraries to avoid "cannot stat" errors
    find build -name "libtivtc.so" -exec cp -v {} /usr/lib/x86_64-linux-gnu/vapoursynth/ \; && \
    find build -name "libtdeint.so" -exec cp -v {} /usr/lib/x86_64-linux-gnu/vapoursynth/ \; && \
    # Note: If libtdm.so is not built, check if it's integrated into libtivtc.so 
    # as TDM functions are part of the TIVTC package.
    find build -name "libtdm.so" -exec cp -v {} /usr/lib/x86_64-linux-gnu/vapoursynth/ \; || true && \
    rm -rf /tmp/tivtc
    
RUN python3 - << 'EOF'
import vapoursynth as vs
core = vs.core
print("znedi3 present:", hasattr(core, "znedi3"))
print("znedi3 funcs:", dir(core.znedi3) if hasattr(core, "znedi3") else "MISSING")
EOF
# STEP 8: Finalize Environment & Patch QTGMC for your specific DePan build
RUN VS_DIR="/usr/lib/x86_64-linux-gnu/vapoursynth" && \
    ln -sf $(find /usr/lib -name "libffms2.so*" | head -n 1) $VS_DIR/libffms2.so && \
    pip3 install numpy && \
    pip3 install havsfunc vsutil --no-deps && \
    pip3 install git+https://github.com/HomeOfVapourSynthEvolution/mvsfunc.git --no-deps && \
    # PATCH: Map standard DePan names to your Gitify build names
    HAVS_PATH=$(python3 -c "import havsfunc; print(havsfunc.__file__)") && \
    sed -i 's/core.depan.Estimate/core.depan.DePanEstimate/g' "$HAVS_PATH" && \
    sed -i 's/core.depan.Stabilize/core.depan.DePan/g' "$HAVS_PATH" && \
    # PATCH: Map 'cutoff' to 'offset' for your specific DePan signature
    sed -i 's/cutoff=/offset=/g' "$HAVS_PATH"

WORKDIR /app
CMD ["python3"]
