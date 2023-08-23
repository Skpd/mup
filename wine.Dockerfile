FROM ubuntu-nvidia-vlk:focal

ARG WVERSION="5.17"
ARG WTVERSION="20200412"

ENV WINE_VERSION="${WVERSION}"
ENV PKG_WINE_VERSION="${WVERSION}~${UBUNTU_VERSION}"
ENV WINE_TRICKS_VERSION="${WTVERSION}"

RUN curl -s https://dl.winehq.org/wine-builds/winehq.key | apt-key add - && \
    echo "deb https://dl.winehq.org/wine-builds/ubuntu/ ${UBUNTU_VERSION} main" | tee /etc/apt/sources.list.d/wine.list && \
    apt update && \
    apt install -y winbind cabextract wget fonts-wine ttf-mscorefonts-installer\
        winehq-staging=$PKG_WINE_VERSION \
        wine-staging=$PKG_WINE_VERSION \
        wine-staging-i386=$PKG_WINE_VERSION \
        wine-staging-amd64=$PKG_WINE_VERSION

ADD https://github.com/Winetricks/winetricks/archive/${WINE_TRICKS_VERSION}.zip /tmp/wt.zip
RUN unzip /tmp/wt.zip -d /tmp/ && \
    cp /tmp/winetricks-${WINE_TRICKS_VERSION}/src/winetricks /usr/local/bin && \
    rm -Rf /tmp/*

RUN useradd --create-home --shell /bin/bash mu
USER mu

ENTRYPOINT ["bash"]