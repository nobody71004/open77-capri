// Compile check for redscript without the error popup.
// Calls the game's own scc_lib.dll (REDscript) the way scc.exe does, but with
// scc_settings_disable_error_popup, so a failed check never shows a dialog on the
// desktop. Usage: MoScc.exe <dir with scc_lib.dll> <sandbox r6 dir> <cache file> [extra script dir]...
using System;
using System.Runtime.InteropServices;
using System.Text;

static class MoScc
{
    const string Lib = "scc_lib.dll";

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool SetDllDirectory(string path);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    static extern IntPtr scc_settings_new(byte[] r6Dir);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    static extern void scc_settings_set_custom_cache_file(IntPtr settings, byte[] path);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    static extern void scc_settings_add_script_path(IntPtr settings, byte[] path);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    static extern void scc_settings_disable_error_popup(IntPtr settings);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    static extern IntPtr scc_compile(IntPtr settings);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    static extern IntPtr scc_get_success(IntPtr result);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    static extern UIntPtr scc_copy_error(IntPtr result, byte[] buffer, UIntPtr size);

    [DllImport(Lib, CallingConvention = CallingConvention.Cdecl)]
    static extern void scc_free_result(IntPtr result);

    static byte[] Z(string s)
    {
        return Encoding.UTF8.GetBytes(s + "\0");
    }

    static int Main(string[] args)
    {
        if (args.Length < 3)
        {
            Console.Error.WriteLine("usage: MoScc <scc_lib dir> <r6 dir> <cache file> [script dir]...");
            return 2;
        }
        SetDllDirectory(args[0]);
        IntPtr settings = scc_settings_new(Z(args[1]));
        scc_settings_set_custom_cache_file(settings, Z(args[2]));
        for (int i = 3; i < args.Length; i++)
        {
            scc_settings_add_script_path(settings, Z(args[i]));
        }
        scc_settings_disable_error_popup(settings);
        IntPtr result = scc_compile(settings);
        bool ok = scc_get_success(result) != IntPtr.Zero;
        if (!ok)
        {
            byte[] buffer = new byte[65536];
            ulong copied = (ulong)scc_copy_error(result, buffer, (UIntPtr)buffer.Length);
            Console.WriteLine("COMPILE FAILED: " + Encoding.UTF8.GetString(buffer, 0, (int)Math.Min(copied, (ulong)buffer.Length)));
        }
        else
        {
            Console.WriteLine("COMPILE OK");
        }
        scc_free_result(result);
        return ok ? 0 : 1;
    }
}
