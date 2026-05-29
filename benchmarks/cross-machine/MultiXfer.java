import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.file.*;
import java.util.concurrent.*;

/**
 * Multi-stream cross-machine transfer. N parallel TCP connections,
 * each transferring a segment of the file.
 */
public class MX {
    static final int BUF = 1048576;
    static final int STREAMS = 4;
    
    public static void main(String[] args) throws Exception {
        String mode = args.length > 0 ? args[0] : "sender";
        if (mode.equals("receiver")) receive();
        else send(args.length > 1 ? args[1] : "fc07:2::1:a:24");
    }
    
    static void send(String host) throws Exception {
        Path src = Paths.get("/dcache/dcache/diskpool01test/data/migtest_001.dat");
        long totalSize = src.toFile().length();
        long segSize = totalSize / STREAMS;
        
        System.out.printf("Sending %d MB via %d streams\n", totalSize/1048576, STREAMS);
        
        CountDownLatch latch = new CountDownLatch(STREAMS);
        long t0 = System.nanoTime();
        long[] sent = new long[STREAMS];
        
        for (int s = 0; s < STREAMS; s++) {
            final int streamId = s;
            final long offset = s * segSize;
            final long size = (s == STREAMS-1) ? totalSize - offset : segSize;
            
            new Thread(() -> {
                try {
                    Socket sock = new Socket(host, 9999);
                    DataOutputStream out = new DataOutputStream(new BufferedOutputStream(sock.getOutputStream(), 65536));
                    out.writeInt(streamId); out.writeLong(offset); out.writeLong(size); out.flush();
                    
                    // Async reads for this segment
                    int N = 8;
                    AsynchronousFileChannel afc = AsynchronousFileChannel.open(src, StandardOpenOption.READ);
                    ByteBuffer[] bufs = new ByteBuffer[N];
                    Future<Integer>[] reads = (Future<Integer>[])new Future[N];
                    long chunks = size / BUF;
                    for(int i=0;i<N&&i<chunks;i++){bufs[i]=ByteBuffer.allocateDirect(BUF);bufs[i].limit((int)Math.min(BUF,size-i*BUF));reads[i]=afc.read(bufs[i],(offset/BUF+i)*BUF);}
                    
                    long ns=0,slot=0;
                    for(long seq=0;seq<chunks;seq++){
                        reads[(int)slot].get(); ByteBuffer buf=bufs[(int)slot]; buf.flip();
                        byte[] bytes = new byte[buf.remaining()]; buf.get(bytes);
                        out.write(bytes); ns += bytes.length;
                        if(seq+N<chunks){long pos=offset+(seq+N)*BUF;bufs[(int)slot].clear();bufs[(int)slot].limit((int)Math.min(BUF,size-(seq+N)*BUF));reads[(int)slot]=afc.read(bufs[(int)slot],pos);}
                        slot=(slot+1)%N;
                    }
                    afc.close(); out.close(); sock.close();
                    sent[streamId] = ns;
                } catch (Exception e) { System.err.printf("S%d: %s\n", streamId, e); }
                latch.countDown();
            }).start();
        }
        latch.await();
        double sec = (System.nanoTime()-t0)/1e9;
        long total = 0; for(long v : sent) total += v;
        System.out.printf("Sent %d MB in %.1fs: %.1f MB/s (%.1f Gb/s)\n", total/1048576, sec, total/sec/(1024*1024), total/sec*8/1e9);
    }
    
    static void receive() throws Exception {
        ServerSocket ss = new ServerSocket(9999, STREAMS);
        System.out.printf("Receiver on port 9999 for %d streams\n", STREAMS);
        
        CountDownLatch latch = new CountDownLatch(STREAMS);
        long t0 = System.nanoTime();
        long[] received = new long[STREAMS];
        
        for (int i = 0; i < STREAMS; i++) {
            new Thread(() -> {
                try {
                    Socket sock = ss.accept();
                    DataInputStream in = new DataInputStream(new BufferedInputStream(sock.getInputStream(), 65536));
                    int sid = in.readInt();
                    long offset = in.readLong();
                    long size = in.readLong();
                    
                    Path dst = Paths.get("/dcache/dcache/diskpool01test/data/rx_" + sid + ".dat");
                    FileChannel dfc = FileChannel.open(dst, StandardOpenOption.WRITE, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
                    
                    ByteBuffer buf = ByteBuffer.allocateDirect(BUF);
                    long pos = 0;
                    while (pos < size) {
                        buf.clear(); int chunk = (int)Math.min(BUF, size-pos); buf.limit(chunk);
                        byte[] bytes = new byte[chunk]; in.readFully(bytes);
                        buf.put(bytes); buf.flip(); dfc.write(buf); pos += chunk;
                    }
                    dfc.close(); sock.close();
                    received[sid] = size;
                } catch (Exception e) { System.err.println("Rx: " + e); }
                latch.countDown();
            }).start();
        }
        latch.await(); ss.close();
        double sec = (System.nanoTime()-t0)/1e9;
        long total = 0; for(long v : received) total += v;
        System.out.printf("Received %d MB in %.1fs: %.1f MB/s (%.1f Gb/s)\n", total/1048576, sec, total/sec/(1024*1024), total/sec*8/1e9);
        
        // Clean up
        for (int i = 0; i < STREAMS; i++) new File("/dcache/dcache/diskpool01test/data/rx_" + i + ".dat").delete();
    }
}
