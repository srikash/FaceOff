# Start from Ubuntu 18.04
FROM ubuntu:18.04

# Install required packages
RUN apt-get update && \
    apt-get install -y wget unzip

# Download ANTs 2.4.3 and install it
RUN wget https://github.com/ANTsX/ANTs/releases/download/v2.4.3/ants-2.4.3-ubuntu-18.04-X64-gcc.zip && \
    unzip ants-2.4.3-ubuntu-18.04-X64-gcc.zip && \
    rm ants-2.4.3-ubuntu-18.04-X64-gcc.zip && \
    mv ants-2.4.3-ubuntu-18.04-X64-gcc /opt/ants && \
    export ANTSPATH=/opt/ants/bin/

# Clone FaceOff repository and set it as the working directory
RUN apt-get update && \
    apt-get install -y git && \
    git clone https://github.com/srikash/FaceOff.git /opt/FaceOff
WORKDIR /opt/FaceOff

# Set ANTs path in environment variables
ENV ANTSPATH=/opt/ants/bin/

# Set entry point as FaceOff script
ENTRYPOINT ["/opt/FaceOff/FaceOff"]