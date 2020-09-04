# pom.xml covert to json

## compile

```bash
mvn clean compile assembly:single
```

## run
```bash
java -jar .\pom_convert-1.0-SNAPSHOT-jar-with-dependencies.jar pom.xml depens.json
```

```json
{
   "data":[
      {
         "groupId":"org.apache.maven",
         "artifactId":"maven-model",
         "version":"3.6.3"
      },
      {
         "groupId":"com.alibaba",
         "artifactId":"fastjson",
         "version":"1.2.73"
      }
   ],
   "len":2
}
```