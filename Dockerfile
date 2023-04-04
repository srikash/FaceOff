FROM ubuntu:18.04

# Install required dependencies
RUN apt-get update && \
    apt-get install -y \
        wget \
        unzip \
        build-essential \
        cmake \
        zlib1g-dev \
        libxt-dev \
        libxml2-dev \
        libxslt1-dev \
        libgdcm2-dev \
        libpng-dev \
        libjpeg-dev \
        libboost-dev \
        libeigen3-dev \
        git \
        vim

# Download and install ANTs 2.3.4
WORKDIR /opt
RUN wget https://github.com/ANTsX/ANTs/archive/v2.3.4.tar.gz && \
    tar -zxvf v2.3.4.tar.gz && \
    rm v2.3.4.tar.gz && \
    cd ANTs-2.3.4 && \
    mkdir build && \
    cd build && \
    cmake .. && \
    make -j 4 && \
    make install && \
    cd ../..

# Set ANTSPATH environment variable
ENV ANTSPATH /opt/ANTs-2.3.4/bin/

# Clone FaceOff repository
WORKDIR /opt
RUN git clone https://github.com/srikash/FaceOff.git

# Set entry point
WORKDIR /opt/FaceOff
ENTRYPOINT ["/opt/FaceOff/FaceOff"]