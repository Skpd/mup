// Decompiles every function that calls winsock send (ws2_32 ordinal 19), directly or through its thunk.
// args: <output file>
//@category mu

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.ExternalLocation;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.Symbol;

public class DumpSenders extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();

        // targets: the send import itself plus any thunk jumping to it
        List<Address> targets = new ArrayList<>();
        for (Symbol s : currentProgram.getSymbolTable().getExternalSymbols()) {
            ExternalLocation loc = currentProgram.getExternalManager().getExternalLocation(s);
            if (loc != null && "Ordinal_19".equals(loc.getLabel()) && loc.getLibraryName().equalsIgnoreCase("WS2_32.DLL")) {
                for (Reference r : getReferencesTo(s.getAddress())) {
                    targets.add(r.getFromAddress());
                }
            }
        }

        Map<Address, List<Address>> sites = new TreeMap<>();
        List<Address> pending = new ArrayList<>(targets);
        for (Address t : targets) {
            Function thunk = getFunctionContaining(t);
            if (thunk != null && thunk.getBody().getNumAddresses() <= 8) {
                for (Reference r : getReferencesTo(thunk.getEntryPoint())) {
                    pending.add(r.getFromAddress());
                }
            }
        }
        for (Address a : pending) {
            Function f = getFunctionContaining(a);
            if (f == null || f.getBody().getNumAddresses() <= 8) {
                continue;
            }
            sites.computeIfAbsent(f.getEntryPoint(), k -> new ArrayList<>()).add(a);
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
            for (var e : sites.entrySet()) {
                Function f = getFunctionAt(e.getKey());
                DecompileResults r = decompiler.decompileFunction(f, 300, monitor);
                out.println("// ===== " + f.getName() + " @ " + f.getEntryPoint() + " sends at " + e.getValue());
                if (r.getDecompiledFunction() == null) {
                    out.println("// decompile failed: " + r.getErrorMessage());
                } else {
                    out.println(r.getDecompiledFunction().getC());
                }
            }
        }
        println("functions with send: " + sites.size());
    }
}
