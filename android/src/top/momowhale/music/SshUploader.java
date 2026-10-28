package top.momowhale.music;
import com.jcraft.jsch.JSch;
import com.jcraft.jsch.Session;
import com.jcraft.jsch.ChannelExec;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;
public final class SshUploader {
 private Session session;
 private final ConnectionConfig config;
 public SshUploader(ConnectionConfig value){config=value;}
 public synchronized void close(){if(session!=null){session.disconnect();session=null;}}
 public synchronized void upload(JSONObject data) throws Exception {request("upload-music-state",data);}
 public synchronized JSONObject room(JSONObject data) throws Exception {return request("room-control",data);}
 private JSONObject request(String command,JSONObject data) throws Exception {
  ChannelExec channel=null;
  try {
   if(session==null||!session.isConnected()){
    JSch ssh=new JSch();ssh.setKnownHosts(new ByteArrayInputStream((config.knownHost+"\n").getBytes(StandardCharsets.UTF_8)));
    ssh.addIdentity("whale-music-phone",config.privateKey.getBytes(StandardCharsets.UTF_8),null,null);
    session=ssh.getSession(config.user,config.host,config.port);
    session.setConfig("StrictHostKeyChecking","yes");session.setConfig("PreferredAuthentications","publickey");
    session.setConfig("kex","ecdh-sha2-nistp256");session.setConfig("server_host_key","ecdsa-sha2-nistp256");
    session.setConfig("cipher.c2s","aes128-ctr");session.setConfig("cipher.s2c","aes128-ctr");
    session.setConfig("mac.c2s","hmac-sha2-256");session.setConfig("mac.s2c","hmac-sha2-256");
    session.setConfig("PubkeyAcceptedAlgorithms","rsa-sha2-512,rsa-sha2-256");session.setConfig("compression.c2s","none");session.setConfig("compression.s2c","none");
    session.setTimeout(12000);session.setServerAliveInterval(30000);session.setServerAliveCountMax(2);session.connect(12000);
   }
   channel=(ChannelExec)session.openChannel("exec");channel.setCommand(command);
   channel.setInputStream(new ByteArrayInputStream((data.toString()+"\n").getBytes(StandardCharsets.UTF_8)));
   InputStream in=channel.getInputStream();ByteArrayOutputStream out=new ByteArrayOutputStream();channel.connect(10000);
   long until=System.currentTimeMillis()+22000;byte[] buffer=new byte[1024];
   while(System.currentTimeMillis()<until){while(in.available()>0){int n=in.read(buffer);if(n<0)break;out.write(buffer,0,n);if(out.size()>4096)throw new IllegalStateException("服务器返回过大");}if(channel.isClosed())break;Thread.sleep(50);}
   if(!channel.isClosed())throw new IllegalStateException("同步超时");
   JSONObject reply=new JSONObject(new String(out.toByteArray(),StandardCharsets.UTF_8));
   if(channel.getExitStatus()!=0||!reply.optBoolean("ok")){if("phone_clock_out_of_range".equals(reply.optString("error")))throw new IllegalStateException("请校准手机系统时间");throw new IllegalStateException("room-control".equals(command)?"房间操作未接受，请刷新状态。":"服务器未接受音乐状态");}
   return reply;
  } catch(Exception e){close();throw e;}finally{if(channel!=null)channel.disconnect();}
 }
}
