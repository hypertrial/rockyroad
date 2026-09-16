FROM eclipse-temurin:21-jre-jammy
WORKDIR /work
ARG PLANETILER_VERSION=0.9.0
ADD https://github.com/onthegomap/planetiler/releases/download/v${PLANETILER_VERSION}/planetiler.jar /opt/planetiler.jar
ENTRYPOINT ["java", "-Xmx4g", "-jar", "/opt/planetiler.jar"]
