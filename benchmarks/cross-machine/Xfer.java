import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.file.*;
import java.util.concurrent.*;

public class Xfer {
    static final int BUF = 1048576;
    static final int STREAMS = 4;
    
    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("recv")) { recv(); return; }
        send(args.length > 0 ? args[0] : "fc07:2::1:a:24");
    }
    static void send(String host) throws Exception {
        Path src = Paths.get("/dcache/dcache/diskpool01test/data/migtest_001.dat");
        long total = src.toFile().length(), seg = total / STREAMS;
        System.out.printf("SEND %dMB x %d streams\n", total/1048576, STREAMS);
        CountDownLatch l = new CountDownLatch(STREAMS);
        long t0 = System.nanoTime(), sent[] = new long[STREAMS];
        for(int s=0;s<STREAMS;s++){final int sid=s;final long off=s*seg;final long sz=(s==STREAMS-1)?total-off:seg;
            new Thread(()->{try{
                Socket sock = new Socket(host,9999); OutputStream os = sock.getOutputStream();
                DataOutputStream d = new DataOutputStream(os); d.writeInt(sid); d.writeLong(off); d.writeLong(sz);
                AsynchronousFileChannel afc = AsynchronousFileChannel.open(src,StandardOpenOption.READ);
                ByteBuffer[] bb = new ByteBuffer[8]; Future<Integer>[] rr = (Future<Integer>[])new Future[8];
                long ch=sz/BUF; for(int i=0;i<8&&i<ch;i++){bb[i]=ByteBuffer.allocateDirect(BUF);bb[i].limit((int)Math.min(BUF,sz-i*BUF));rr[i]=afc.read(bb[i],off+i*BUF);}
                long ns=0,slot=0; for(long seq=0;seq<ch;seq++){
                    rr[(int)slot].get(); ByteBuffer b=bb[(int)slot]; b.flip(); byte[] x=new byte[b.remaining()]; b.get(x); os.write(x); ns+=x.length;
                    if(seq+8<ch){long p=off+(seq+8)*BUF;bb[(int)slot].clear();bb[(int)slot].limit((int)Math.min(BUF,sz-(seq+8)*BUF));rr[(int)slot]=afc.read(bb[(int)slot],p);}
                    slot=(slot+1)%8;
                }
                afc.close(); os.close(); sock.close(); sent[sid]=ns;
            }catch(Exception e){System.err.printf("S%d:%s\n",sid,e);} l.countDown();}).start();}
        l.await();
        long tot=0;for(long v:sent)tot+=v;
        double sec=(System.nanoTime()-t0)/1e9;
        System.out.printf("SENT %dMB %.1fs %.1f MB/s (%.1f Gb/s)\n",tot/1048576,sec,tot/sec/(1024*1024),tot/sec*8/1e9);
    }
    static void recv() throws Exception {
        ServerSocket ss = new ServerSocket(9999,STREAMS);
        System.out.printf("RECV on :9999 x %d\n",STREAMS);
        CountDownLatch l = new CountDownLatch(STREAMS);
        long t0=System.nanoTime(),rcvd[]=new long[STREAMS];
        for(int i=0;i<STREAMS;i++){new Thread(()->{try{
            Socket sock = ss.accept(); DataInputStream d=new DataInputStream(sock.getInputStream());
            int sid=d.readInt(); long off=d.readLong(),sz=d.readLong();
            Path dst=Paths.get("/dcache/dcache/diskpool01test/data/rx_"+sid+".dat");
            FileChannel dfc=FileChannel.open(dst,StandardOpenOption.WRITE,StandardOpenOption.CREATE,StandardOpenOption.TRUNCATE_EXISTING);
            ByteBuffer bb=ByteBuffer.allocateDirect(BUF); long pos=0;
            while(pos<sz){bb.clear();int c=(int)Math.min(BUF,sz-pos);bb.limit(c);byte[]x=new byte[c];d.readFully(x);bb.put(x);bb.flip();dfc.write(bb);pos+=c;}
            dfc.close();sock.close();rcvd[sid]=sz;
        }catch(Exception e){System.err.println("R:"+e);} l.countDown();}).start();}
        l.await();ss.close();
        long tot=0;for(long v:rcvd)tot+=v;
        double sec=(System.nanoTime()-t0)/1e9;
        System.out.printf("RECV %dMB %.1fs %.1f MB/s (%.1f Gb/s)\n",tot/1048576,sec,tot/sec/(1024*1024),tot/sec*8/1e9);
        for(int i=0;i<STREAMS;i++)new File("/dcache/dcache/diskpool01test/data/rx_"+i+".dat").delete();
    }
}
