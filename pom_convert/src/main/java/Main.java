
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import org.apache.maven.model.Dependency;
import org.apache.maven.model.Model;
import org.apache.maven.model.io.xpp3.MavenXpp3Reader;
import org.codehaus.plexus.util.xml.pull.XmlPullParserException;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class Main {


    public static String map_var(String string, Properties properties) {
        if (string == null)
            return null;
        final String regex = "\\$\\{(\\S*?)\\}";
        final Pattern pattern = Pattern.compile(regex, Pattern.MULTILINE);
        Matcher matcher = pattern.matcher(string);
        if (matcher.find()) {
            return (String) properties.get(matcher.group(1));
        } else {
            return string;
        }
    }


    public static void main(String[] args) throws IOException, XmlPullParserException {

        FileInputStream fileIn;
        BufferedWriter bufferedWriter;
        try {
            // open input file
            try {
                fileIn = new FileInputStream(args[0]);
            } catch (FileNotFoundException e) {
                System.err.println("Input File Not Found.");
                return;
            }

            // open output file
            try {
                bufferedWriter = new BufferedWriter(new OutputStreamWriter(new FileOutputStream(args[1], false), StandardCharsets.UTF_8));
            } catch (FileNotFoundException e) {
                System.err.println("Error Opening Output File.");
                return;
            }


            MavenXpp3Reader reader = new MavenXpp3Reader();
            Model model = reader.read(fileIn);
            Properties properties = model.getProperties();

            JSONObject json = new JSONObject();
            JSONArray data = new JSONArray();

            if (model.getDependencyManagement() != null && model.getDependencyManagement().getDependencies() != null) {
                for (Dependency dependency : model.getDependencyManagement().getDependencies()) {
                    JSONObject tmp = new JSONObject();
                    tmp.put("groupId", map_var(dependency.getGroupId(), properties));
                    tmp.put("artifactId", map_var(dependency.getArtifactId(), properties));
                    tmp.put("version", map_var(dependency.getVersion(), properties));
                    data.add(tmp);
                }
            }

            if (model.getDependencies() != null) {
                for (Dependency dependency : model.getDependencies()) {
                    JSONObject tmp = new JSONObject();
                    tmp.put("groupId", map_var(dependency.getGroupId(), properties));
                    tmp.put("artifactId", map_var(dependency.getArtifactId(), properties));
                    tmp.put("version", map_var(dependency.getVersion(), properties));
                    data.add(tmp);
                }
            }
            json.put("data", data);
            json.put("len", data.size());
            bufferedWriter.write(json.toJSONString());
            bufferedWriter.flush();
            System.out.printf("Converted pom.xml [%s] file to [%s]", args[0], args[1]);

        } catch (ArrayIndexOutOfBoundsException e) {
            System.err.println("Incorrect argument use:java CopyFile Source Destination");
            return;
        }


    }
}
