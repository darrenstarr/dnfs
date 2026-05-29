import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.file.*;
import java.util.concurrent.*;

/**
 * Cross-machine transfer benchmark.
 * Reads from local NFS with async pipeline, sends via TCP.
 */
public class XferBench {
    static final int BUF = 1048576;
    
    public static void main(String[] args) throws Exception {
        String mode = args.length > 0 ? args[0] : "sender";
        int port = args.length > 1 ? Integer.parseInt(args[1]) : 9999;
        String host = args.length > 2 ? args[2] : "fc07:2::1:a:24";
        
        if (mode.equals("receiver")) {
            receive(port);
        } else {
            send(host, port);
        }
    }
    
    static void send(String host, int port) throws Exception {
        Path src = Paths.get("/dcache/dcache/diskpool01test/data/migtest_001.dat");
        long size = src.toFile().length();
        long chunks = size / BUF;
        int N = 16; // concurrent reads
        
        System.out.printf("Sending %d MB to %s:%d with %d concurrent reads\n", size/1048576, host, port, N);
        
        SocketChannel sock = SocketChannel.open(new InetSocketAddress(host, port));
        DataOutputStream out = new DataOutputStream(new BufferedOutputStream(sock.socket().getOutputStream(), BUF));
        out.writeLong(size); out.flush();
        
        AsynchronousFileChannel afc = AsynchronousFileChannel.open(src, StandardOpenOption.READ);
        ByteBuffer[] bufs = new ByteBuffer[N];
        Future<Integer>[] reads = (Future<Integer>[])new Future[N];
        for(int i=0;i<N&&i<chunks;i++){bufs[i]=ByteBuffer.allocateDirect(BUF);bufs[i].limit((int)Math.min(BUF,size-i*BUF));reads[i]=afc.read(bufs[i],i*BUF);}
        
        long t0=System.nanoTime(),nextSeq=N,slot=0;
        long sent = 0;
        for(long seq=0;seq<chunks;seq++){
            reads[(int)slot].get(); ByteBuffer buf=bufs[(int)slot]; buf.flip();
            while(buf.hasRemaining()) sock.write(buf);
            sent += buf.limit();
            if(nextSeq<chunks){bufs[(int)slot].clear();bufs[(int)slot].limit((int)Math.min(BUF,size-nextSeq*BUF));reads[(int)slot]=afc.read(bufs[(int)slot],nextSeq*BUF);nextSeq++;}
            slot=(slot+1)%N;
        }
        sock.close(); afc.close();
        double sec=(System.nanoTime()-t0)/1e9;
        System.out.printf("Sent %d MB in %.1fs: %.1f MB/s (%.1f Gb/s)\n", sent/1048576, sec, sent/sec/(1024*1024), sent/sec*8/1e9);
    }
    
    static void receive(int port) throws Exception {
        ServerSocketChannel ssc = ServerSocketChannel.open();
        ssc.bind(new InetSocketAddress(port));
        System.out.printf("Listening on port %d\n", port);
        
        SocketChannel sock = ssc.accept();
        System.out.println("Connected");
        
        DataInputStream in = new DataInputStream(new BufferedInputStream(sock.socket().getInputStream(), BUF));
        long size = in.readLong();
        Path dst = Paths.get("/dcache/dcache/diskpool01test/data/received.dat");
        FileChannel dfc = FileChannel.open(dst, StandardOpenOption.WRITE, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
        
        long t0=System.nanoTime(),received=0;
        ByteBuffer buf = ByteBuffer.allocateDirect(BUF);
        while(received < size) {
            buf.clear(); buf.limit((int)Math.min(BUF, size-received));
            while(buf.hasRemaining()) { int n=sock.read(buf); if(n<0)break; }
            buf.flip(); dfc.write(buf); received+=buf.limit();
        }
        dfc.close(); sock.close(); ssc.close();
        double sec=(System.nanoTime()-t0)/1e9;
        System.out.printf("Received %d MB in %.1fs: %.1f MB/s (%.1f Gb/s)\n", received/1048576, sec, received/sec/(1024*1024), received/sec*8/1e9);
        dst.toFile().delete();
    }
}
