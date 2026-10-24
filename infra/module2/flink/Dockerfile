FROM maven:3.9.11-eclipse-temurin-17 AS build
WORKDIR /build
COPY pom.xml .
COPY src src
RUN mvn -q -DskipTests package

FROM flink:1.20.5-scala_2.12-java17
COPY --from=build /build/target/cogniflow-streaming.jar /opt/flink/usrlib/cogniflow-streaming.jar
