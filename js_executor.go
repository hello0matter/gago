// 文件: js_executor.go
package main

import (
	"fmt"
	"log"
	"os"

	"github.com/dop251/goja"
)

// JsExecutor 结构体，封装了JS虚拟机和所需功能
type JsExecutor struct {
	vm *goja.Runtime
}

// NewJsExecutor 创建并初始化一个新的JS执行器
func NewJsExecutor() (*JsExecutor, error) {
	// ==================================================================
	//  ↓ ↓ ↓ ↓ ↓ ↓ 在这里填充你需要的所有JS代码 ↓ ↓ ↓ ↓ ↓ ↓
	// ==================================================================
	// 您需要把 i1a, Sha, _.Id 以及它们所有的依赖函数的JS代码
	// 从浏览器扒出来，然后粘贴到 "google_crypto.js" 这个文件里。
	// 这是一个巨大的体力活，也是补环境最关键的一步。

	jsCode, err := os.ReadFile("google_crypto.js")
	if err != nil {
		// 如果文件不存在，给一个明确的提示
		log.Println("错误: 未找到 'google_crypto.js' 文件。请创建这个文件并填入所有依赖的JS代码。")
		return nil, fmt.Errorf("读取JS文件失败: %w", err)
	}

	vm := goja.New()
	// 执行所有JS代码，让所有函数在虚拟机里“就位”
	_, err = vm.RunString(string(jsCode))
	if err != nil {
		return nil, fmt.Errorf("执行JS代码失败: %w", err)
	}

	return &JsExecutor{vm: vm}, nil
}

// GenerateGsLp 是我们暴露给主流程的唯一接口
// 它模拟了浏览器中生成 gs_lp 的完整过程
func (je *JsExecutor) GenerateGsLp(query string, pageData *GooglePageData) (string, error) {
	// =================================================================
	// 1. 调用 i1a 函数，生成序列化的数据包
	// =================================================================

	// 我们需要一个JS包装函数来处理 `this` 上下文
	// 请在您的 "google_crypto.js" 文件中加入类似下面的包装函数：
	/*
		function call_i1a(query, context) {
			// context 是从Go传过来的对象，包含了 this.s$, this.Na 等等
			// 在这里构建一个假的`this`对象
			var fake_this = context;

			// 确保原始的 i1a 函数能被调用，并且绑定了我们伪造的 this
			// 假设原始函数名为 original_i1a
			// return original_i1a.call(fake_this, query);

			// **注意**: i1a的返回值可能是一个复杂的对象或数组，而不是可以直接用的字节数组。
			// 您可能需要进一步处理它，比如调用它的 .serialize() 方法。
			// 假设最终的序列化字节数组是通过 a.m.ia 得到的:
			var protobuf_obj = original_i1a.call(fake_this, query);
			return protobuf_obj.m.ia; // 返回 Uint8Array
		}
	*/

	i1aWrapper, ok := goja.AssertFunction(je.vm.Get("call_i1a"))
	if !ok {
		return "", fmt.Errorf("在JS环境中找不到 'call_i1a' 函数")
	}

	// TODO: 构建传递给 call_i1a 的 context 对象
	// 这是技术活，需要您在浏览器里断点调试，看看 i1a 用到了 this 的哪些属性
	jsContext := map[string]interface{}{
		"s$": 18,                    // 这是一个示例，您需要填写真实的值
		"oa": pageData.ClickCounter, // 示例
		"Na": goja.Undefined(),      // 如果Na是函数，需要特殊处理
		// ... 填充所有 i1a 用到的 this 属性 ...
	}

	// 调用JS函数
	i1aResult, err := i1aWrapper(goja.Undefined(), je.vm.ToValue(query), je.vm.ToValue(jsContext))
	if err != nil {
		return "", fmt.Errorf("调用 'call_i1a' 失败: %w", err)
	}

	// 将JS返回的 Uint8Array 转换为 Go的 []byte
	protoBytes, ok := i1aResult.Export().([]byte)
	if !ok {
		return "", fmt.Errorf("i1a 的JS返回值无法转换为 []byte")
	}

	// =================================================================
	// 2. 调用 GPg (Sha) 函数，计算哈希
	// =================================================================
	// 假设 GPg 就是 Sha 函数的别名
	gpgFunc, ok := goja.AssertFunction(je.vm.Get("GPg"))
	if !ok {
		return "", fmt.Errorf("在JS环境中找不到 'GPg' 函数")
	}

	hashResult, err := gpgFunc(goja.Undefined(), je.vm.ToValue(protoBytes))
	if err != nil {
		return "", fmt.Errorf("调用 'GPg' 失败: %w", err)
	}
	hashBytes, ok := hashResult.Export().([]byte)
	if !ok {
		return "", fmt.Errorf("GPg 的JS返回值无法转换为 []byte")
	}

	// =================================================================
	// 3. 调用 _.Id 函数，进行自定义Base64编码
	// =================================================================
	idFunc, ok := goja.AssertFunction(je.vm.Get("Id_wrapper")) // 假设你创建了一个wrapper
	if !ok {
		return "", fmt.Errorf("在JS环境中找不到 'Id_wrapper' 函数")
	}

	// 在 "google_crypto.js" 中加入:
	// function Id_wrapper(data) { return _.Id(data, 4); }

	gsLpResult, err := idFunc(goja.Undefined(), je.vm.ToValue(hashBytes))
	if err != nil {
		return "", fmt.Errorf("调用 'Id_wrapper' 失败: %w", err)
	}

	return gsLpResult.String(), nil
}
