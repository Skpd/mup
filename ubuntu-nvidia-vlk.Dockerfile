ARG UBUNTU_VERSION=focal
ARG NVIDIA_DRIVER_VERSION=535
FROM ubuntu:$UBUNTU_VERSION

ARG UBUNTU_VERSION
ARG NVIDIA_DRIVER_VERSION

ENV DEBIAN_FRONTEND=noninteractive
ENV UBUNTU_VERSION=$UBUNTU_VERSION
ENV NVIDIA_DRIVER_VERSION=$NVIDIA_DRIVER_VERSION

RUN dpkg --add-architecture i386 && \
    apt update && \
    apt install -y gnupg2 apt-transport-https curl

RUN apt install -y  \
    nvidia-driver-${NVIDIA_DRIVER_VERSION}  \
    libnvidia-gl-${NVIDIA_DRIVER_VERSION}:i386  \
    libvulkan1  \
    libvulkan1:i386  \
    vulkan-tools  \
    vulkan-utils