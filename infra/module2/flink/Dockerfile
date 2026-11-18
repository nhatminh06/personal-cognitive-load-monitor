FROM maven:3.9.11-eclipse-temurin-17 AS build
WORKDIR /build
COPY infra/module2/flink/pom.xml .
COPY infra/module2/flink/src src
COPY tests/fixtures /tests/fixtures
RUN MAVEN_OPTS="-Xmx1024m -XX:ActiveProcessorCount=2" mvn -q test package \
    && MAVEN_OPTS="-Xmx1024m -XX:ActiveProcessorCount=2" mvn -q dependency:copy \
    -Dartifact=org.apache.flink:flink-metrics-prometheus:1.20.5 \
    -DoutputDirectory=/build/metrics

FROM flink:1.20.5-scala_2.12-java17
USER root
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
COPY --from=build /build/target/cogniflow-streaming.jar /opt/flink/usrlib/cogniflow-streaming.jar
COPY --from=build /build/metrics/flink-metrics-prometheus-1.20.5.jar /opt/flink/lib/

USER flink
