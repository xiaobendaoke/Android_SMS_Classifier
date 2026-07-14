# Gradle Wrapper

本项目使用 Gradle 8.7 Wrapper（`gradle/wrapper/gradle-wrapper.properties`）。

## 当前状态（阶段 0）

- `gradlew` / `gradlew.bat` 脚本已创建
- **`gradle-wrapper.jar` 可能缺失** — 首次构建前需生成或下载

## 生成 Wrapper JAR

在已安装 Gradle 的机器上：

```bash
cd android
gradle wrapper --gradle-version 8.7
```

或从官方 Gradle 发行版复制 `gradle/wrapper/gradle-wrapper.jar`（Apache-2.0）。

## 构建前提

- JDK 17+
- Android SDK（`compileSdk 34`，`minSdk 26`）
- 设置 `ANDROID_HOME` 或 `local.properties` 中的 `sdk.dir`

```properties
# android/local.properties（不入 Git）
sdk.dir=/path/to/Android/Sdk
```

## 验证

```bash
cd android
./gradlew test
./gradlew :app:assembleDebug
```

若 `./gradlew` 报错 `Could not find or load main class org.gradle.wrapper.GradleWrapperMain`，说明缺少 `gradle-wrapper.jar`，请按上文步骤补齐。
