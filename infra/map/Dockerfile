FROM eclipse-temurin:21-jre-jammy
WORKDIR /work
ARG PLANETILER_VERSION=0.9.0
ADD https://github.com/onthegomap/planetiler/releases/download/v${PLANETILER_VERSION}/planetiler.jar /opt/planetiler.jar
ENV JAVA_TOOL_OPTIONS="-Xmx4g"
ENTRYPOINT ["java", "-jar", "/opt/planetiler.jar"]
