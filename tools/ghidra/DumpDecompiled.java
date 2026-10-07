// Decompiles the functions containing the given addresses.
// args: <output file> <address or @file with one address per line> [...]
//@category mu

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;

public class DumpDecompiled extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);

        List<String> addresses = new ArrayList<>();
        for (int i = 1; i < args.length; i++) {
            if (args[i].startsWith("@")) {
                addresses.addAll(Files.readAllLines(Path.of(args[i].substring(1))));
            } else {
                addresses.add(args[i]);
            }
        }

        try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
            for (String address : addresses) {
                if (address.isBlank()) {
                    continue;
                }
                Function f = getFunctionContaining(toAddr(address.trim()));
                if (f == null) {
                    out.println("// no function at " + address);
                    continue;
                }

                DecompileResults r = decompiler.decompileFunction(f, 300, monitor);
                out.println("// ===== " + f.getName() + " @ " + f.getEntryPoint());
                if (r.getDecompiledFunction() == null) {
                    out.println("// decompile failed: " + r.getErrorMessage());
                } else {
                    out.println(r.getDecompiledFunction().getC());
                }
            }
        }
    }
}
